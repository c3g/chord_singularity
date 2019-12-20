#!/usr/bin/env python3

import json
import os
import subprocess
import sys

from jsonschema import validate
from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import AUTH_CONFIG_PATH, get_config_vars, TYPE_PYTHON, TYPE_JAVASCRIPT

# threads = 4 to allow some "parallel" requests; important for peer discovery/confirmation.
UWSGI_CONF_TEMPLATE = """[uwsgi]
vhost = true
manage-script-name = true
enable-threads = true
threads = 4  # enables enable-threads by default, but we explicitly set it to true anyway
socket = {service_socket}
venv = {service_venv}
chdir = /chord/services/{service_artifact}
mount = /api/{service_artifact}={service_python_module}:{service_python_callable}
vacuum = true
"""

NGINX_CONF_LOCATION = "/usr/local/openresty/nginx/conf/nginx.conf"

NGINX_CONF_HEADER = """
daemon off;

worker_processes 1;
pid /chord/tmp/nginx.pid;

events {
  worker_connections 1024;
}

http {
  # include /etc/nginx/mime.types;
  default_type application/octet-stream;
  
  client_body_temp_path /chord/tmp/nginx/client_tmp;
  proxy_temp_path /chord/tmp/nginx/proxy_tmp;
  fastcgi_temp_path /chord/tmp/nginx/fastcgi_tmp;
  uwsgi_temp_path /chord/tmp/nginx/uwsgi_tmp;
  scgi_temp_path /chord/tmp/nginx/scgi_tmp;

  sendfile off;
  keepalive_timeout 600;
  
  server_names_hash_bucket_size 128;

  index index.html index.htm;

  # lua-resty-openidc global configuration
  resolver 8.8.8.8;  # resolve OIDC URLs with Google DNS
  lua_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
  lua_ssl_verify_depth 5;
  lua_shared_dict discovery 1m;
  lua_shared_dict jwks 1m;

"""

# TODO: redirect_uri
# TODO: PROD: SSL VERIFY
NGINX_CONF_SERVER_HEADER = """
  server {{
    listen unix:/chord/tmp/nginx.sock;
    root /chord/web/public;
    index index.html index.htm index.nginx-debian.html;
    server_name _;

    location / {{
      try_files $uri /index.html;
    }}

    location /dist/ {{
      alias /chord/web/dist/;
    }}

    location /api/ {{
      access_by_lua_block {{
        local auth_file = assert(io.open("{auth_config}"))
        local auth_params = require("cjson").decode(auth_file:read("*all"))
        auth_file:close()
        local opts = {{
          redirect_uri = "/api/callback",
          discovery = auth_params["OIDC_DISCOVERY_URI"],
          client_id = auth_params["CLIENT_ID"],
          client_secret = auth_params["CLIENT_SECRET"],
          accept_unsupported_alg = false,
        }}
        local res, err = require("resty.openidc").authenticate(
          opts,
          nil,
          (function ()
             if ngx.var.uri and ngx.var.uri == "/api/authenticate"
               then return nil
               else return "pass"
             end
           end)()
        )
        if err then
          ngx.status = 500
          ngx.say(err)
          ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
        end
        if res == nil then
          -- If authenticate hasn't rejected us above but it's "open", i.e.
          -- non-authenticated users can see the page, clear the X-User header.
          ngx.req.set_header("X-User", nil)
        else
          ngx.req.set_header("X-User", res.id_token.sub)
        end
      }}
"""

NGINX_CONF_FOOTER = """
  }
}
"""

NGINX_SERVICE_UPSTREAM_TEMPLATE = """
upstream chord_{s_artifact} {{
  server unix:{s_socket};
}}
"""

NGINX_SERVICE_BASE_TEMPLATE = """
location = {base_url} {{
  rewrite ^ {base_url}/;
}}
location {base_url} {{
  try_files $uri @{s_artifact};
}}
"""

NGINX_SERVICE_WSGI_TEMPLATE = """
location @{s_artifact} {{
  include            uwsgi_params;
  uwsgi_param        Host              $http_host;
  uwsgi_param        X-Real-IP         $remote_addr;
  uwsgi_param        X-Forwarded-For   $proxy_add_x_forwarded_for;
  uwsgi_param        X-Forwarded-Proto $http_x_forwarded_proto;
  uwsgi_pass         chord_{s_artifact};
  uwsgi_read_timeout 600;
  uwsgi_send_timeout 600;
  send_timeout       600;
}}
"""

NGINX_SERVICE_NON_WSGI_TEMPLATE = """
location @{s_artifact} {{
  proxy_http_version 1.1;
  proxy_pass_header  Server;
  proxy_set_header   Upgrade           $http_upgrade;
  proxy_set_header   Connection        "upgrade";
  proxy_set_header   Host              $http_host;
  proxy_set_header   X-Real-IP         $remote_addr;
  proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header   X-Forwarded-Proto $http_x_forwarded_proto;
  proxy_pass         http://chord_{s_artifact};
  proxy_read_timeout 600;
  proxy_send_timeout 600;
  send_timeout       600;
}}
"""


def generate_uwsgi_confs(services: List[Dict], services_config_path: str):
    uwsgi_confs = []

    for s in services:
        if not s.get("wsgi", True):
            continue

        config_vars = get_config_vars(s, services_config_path)

        uwsgi_conf = UWSGI_CONF_TEMPLATE.format(
            service_artifact=config_vars["SERVICE_ARTIFACT"],
            service_socket=config_vars["SERVICE_SOCKET"],
            service_venv=config_vars["SERVICE_VENV"],
            service_python_module=s["python_module"],
            service_python_callable=s["python_callable"]
        )

        if "python_args" in s:
            uwsgi_conf += f"pyargv = {' '.join(a.format(**config_vars) for a in s['python_args'])}\n"

        # Import configuration environment variables into uWSGI environment
        uwsgi_conf += f"for-readline = {config_vars['SERVICE_ENVIRONMENT']}\n"
        uwsgi_conf += "  env = %(_)\n"
        uwsgi_conf += "endfor =\n"

        if "run_environment" in s:
            for e, val in s["run_environment"].items():
                uwsgi_conf += f"env = {e}={val.format(**config_vars)}\n"

        uwsgi_confs.append(uwsgi_conf)

    return uwsgi_confs


def generate_nginx_conf(services: List[Dict], services_config_path: str):
    nginx_conf = NGINX_CONF_HEADER

    for s in services:
        config_vars = get_config_vars(s, services_config_path)
        nginx_conf += NGINX_SERVICE_UPSTREAM_TEMPLATE.format(s_artifact=config_vars["SERVICE_ARTIFACT"],
                                                             s_socket=config_vars["SERVICE_SOCKET"])

    nginx_conf += NGINX_CONF_SERVER_HEADER.format(auth_config=AUTH_CONFIG_PATH)

    # Service location wrappers
    for s in services:
        config_vars = get_config_vars(s, services_config_path)
        nginx_conf += NGINX_SERVICE_BASE_TEMPLATE.format(base_url=config_vars["SERVICE_URL_BASE_PATH"],
                                                         s_artifact=config_vars["SERVICE_ARTIFACT"])

    nginx_conf += "\n    }\n"

    # Named locations
    for s in services:
        config_vars = get_config_vars(s, services_config_path)
        nginx_conf += (NGINX_SERVICE_WSGI_TEMPLATE if "wsgi" not in s or s["wsgi"]
                       else NGINX_SERVICE_NON_WSGI_TEMPLATE).format(s_artifact=config_vars["SERVICE_ARTIFACT"])

    nginx_conf += NGINX_CONF_FOOTER

    return nginx_conf


def main():
    args = sys.argv[1:]

    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} chord_services.json chord_services_config.json")
        exit(1)

    if os.environ.get("SINGULARITY_ENVIRONMENT", "") == "":
        print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity container.")
        exit(1)

    with open("/chord/chord_services.schema.json") as cf, open(args[0], "r") as sf:
        schema = json.load(cf)
        services = json.load(sf)

        validate(instance=services, schema=schema)

        services_config_path = args[1]

        # STEP 1: Install deduplicated apt dependencies.

        print("[CHORD Container Setup] Installing apt dependencies...")

        apt_dependencies = set()
        for s in services:
            apt_dependencies = apt_dependencies.union(s.get("apt_dependencies", ()))

        subprocess.run(("apt-get", "install", "-y") + tuple(apt_dependencies), stdout=subprocess.DEVNULL, check=True)

        # STEP 2: Run pre-install commands

        print("[CHORD Container Setup] Running service pre-install commands...")

        for s in services:
            commands = s.get("pre_install_commands", ())
            for c in commands:
                print("[CHORD Container Setup]    {}".format(c))
                subprocess.run(c, shell=True, check=True, stdout=subprocess.DEVNULL)

        # STEP 3: Create virtual environments and install packages

        print("[CHORD Container Setup] Creating virtual environments...")

        for s in services:
            s_artifact = s["type"]["artifact"]

            subprocess.run(f"/bin/bash -c 'mkdir -p /chord/services/{s_artifact}'", shell=True, check=True)

            if s["type"]["language"] == TYPE_PYTHON:
                subprocess.run(
                    f"/bin/bash -c 'cd /chord/services/{s_artifact}; "
                    f"              python3.7 -m virtualenv -p python3.7 env; "
                    f"              source env/bin/activate; "
                    f"              pip install --no-cache-dir git+{s['repository']};"
                    f"              deactivate'",
                    shell=True,
                    check=True,
                    stdout=subprocess.DEVNULL
                )

            elif s["type"]["language"] == TYPE_JAVASCRIPT:
                subprocess.run(
                    f"/bin/bash -c 'cd /chord/services/{s_artifact}; "
                    f"              npm install -g {s['repository']}'",
                    shell=True,
                    check=True,
                    stdout=subprocess.DEVNULL
                )

            else:
                raise NotImplementedError(f"Unknown language: {s['type']['language']}")

        os.chdir("/chord")

        # STEP 4: Generate uWSGI configuration files

        print("[CHORD Container Setup] Generating uWSGI configuration files...")

        for s, c in zip((s2 for s2 in services if s2.get("wsgi", True)),
                        generate_uwsgi_confs(services, services_config_path)):
            conf_path = f"/chord/vassals/{s['type']['artifact']}.ini"

            if os.path.exists(conf_path):
                print(f"Error: File already exists: '{conf_path}'", file=sys.stderr)
                exit(1)

            with open(conf_path, "w") as uf:
                uf.write(c)

        # STEP 5: Generate NGINX configuration file

        print("[CHORD Container Setup] Generating NGINX configuration file...")

        with open(NGINX_CONF_LOCATION, "w") as nf:
            nf.write(generate_nginx_conf(services, services_config_path))


if __name__ == "__main__":
    main()
