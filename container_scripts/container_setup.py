#!/usr/bin/env python3

import json
import os
import subprocess
import sys

from jsonschema import validate
from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import AUTH_CONFIG_PATH, INSTANCE_CONFIG_PATH, get_config_vars, TYPE_PYTHON, TYPE_JAVASCRIPT

# threads = 4 to allow some "parallel" requests; important for peer discovery/confirmation.
UWSGI_CONF_TEMPLATE = """[uwsgi]
vhost = true
manage-script-name = true
enable-threads = true
lazy-apps = true  # use pre-forking instead, to prevent threading headaches
buffer-size = 32768  # allow reading of larger headers, for e.g. auth
socket = {service_socket}
venv = {service_venv}
chdir = /chord/services/{service_artifact}
mount = /api/{service_artifact}={service_python_module}:{service_python_callable}
vacuum = true
"""

NGINX_CONF_LOCATION = "/usr/local/openresty/nginx/conf/nginx.conf"
NGINX_UPSTREAMS_CONF_LOCATION = "/usr/local/openresty/nginx/conf/chord_upstreams.conf"
NGINX_SERVICES_CONF_LOCATION = "/usr/local/openresty/nginx/conf/chord_services.conf"

# TODO: PROD: SSL VERIFY AUTH
NGINX_CONF_TEMPLATE = """
daemon off;

worker_processes 1;
pid /chord/tmp/nginx.pid;

events {{
  worker_connections 1024;
}}

http {{
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

  # Explicitly prevent underscores in headers from being passed, even though
  # off is the default. This prevents auth header forging.
  # e.g. https://docs.djangoproject.com/en/3.0/howto/auth-remote-user/
  underscores_in_headers off;

  include {upstreams_conf};

  limit_req_zone $binary_remote_addr zone=external:10m rate=10r/s;

  server {{
    listen unix:/chord/tmp/nginx.sock;
    server_name _;

    # Enable to show debugging information in the error log:
    # error_log /usr/local/openresty/nginx/logs/error.log debug;

    # lua-resty-session configuration
    # - use Redis for sessions to allow scaling of NGINX
    set $session_cookie_lifetime 180s;
    set $session_cookie_renew    180s;
    set $session_storage         redis;
    set $session_redis_prefix    oidc;
    set $session_redis_socket    unix:///chord/tmp/redis.sock;

    location = /favicon.ico {{
      return 404;
      log_not_found off;
      access_log off;
    }}

    location / {{
      # Set up two-stage rate limiting:
      #   Store:  10 MB worth of IP addresses (~160 000)
      #   Rate:   10 requests per second.
      #   Bursts: Allow for bursts of 20 with no delay and an additional 30
      #          (total 50) queued requests before throwing up 503.
      #   This limit is for requests from outside the DMZ; internal microservices
      #   currently get unlimited access.
      # See: https://www.nginx.com/blog/rate-limiting-nginx/
      limit_req zone=external burst=50 delay=20;

      set $chord_auth_config "{auth_config}";
      set $chord_instance_config "{instance_config}";
      access_by_lua_file /chord/container_scripts/proxy_auth.lua;

      # TODO: Deduplicate with below?
      proxy_http_version 1.1;
      proxy_pass_header  Server;
      proxy_set_header   Upgrade           $http_upgrade;
      proxy_set_header   Connection        "upgrade";
      proxy_set_header   Host              $http_host;
      proxy_set_header   X-Real-IP         $remote_addr;
      proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
      proxy_set_header   X-Forwarded-Proto $http_x_forwarded_proto;
      proxy_pass         http://unix:/chord/tmp/nginx_internal.sock;
      proxy_read_timeout 660s;
      proxy_send_timeout 660s;
      send_timeout       660s;
    }}
  }}

  server {{
    listen unix:/chord/tmp/nginx_internal.sock;
    root /chord/web/public;
    index index.html index.htm index.nginx-debian.html;
    server_name _;

    location / {{
      try_files $uri /index.html;
    }}

    location /dist/ {{
      alias /chord/web/dist/;
    }}

    include {services_conf};
  }}
}}
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
  uwsgi_param        Host            $http_host;
  uwsgi_param        X-Forwarded-For $proxy_add_x_forwarded_for;
  uwsgi_pass         chord_{s_artifact};
  uwsgi_read_timeout 600s;
  uwsgi_send_timeout 600s;
  send_timeout       600s;
}}
"""

NGINX_SERVICE_NON_WSGI_TEMPLATE = """
location @{s_artifact} {{
  proxy_http_version 1.1;
  proxy_pass_header  Server;
  proxy_set_header   Upgrade           $http_upgrade;
  proxy_set_header   Connection        "upgrade";
  proxy_pass_header  Host;
  proxy_pass_header  X-Real-IP;
  proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_pass_header  X-Forwarded-Proto;
  proxy_pass         http://chord_{s_artifact};
  proxy_read_timeout 600s;
  proxy_send_timeout 600s;
  send_timeout       600s;
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


def generate_nginx_confs(services: List[Dict], services_config_path: str):
    nginx_conf = NGINX_CONF_TEMPLATE.format(upstreams_conf=NGINX_UPSTREAMS_CONF_LOCATION,
                                            services_conf=NGINX_SERVICES_CONF_LOCATION,
                                            auth_config=AUTH_CONFIG_PATH,
                                            instance_config=INSTANCE_CONFIG_PATH)

    nginx_upstreams_conf = ""
    nginx_services_conf = ""

    for s in services:
        config_vars = get_config_vars(s, services_config_path)

        # Upstream
        nginx_upstreams_conf += NGINX_SERVICE_UPSTREAM_TEMPLATE.format(s_artifact=config_vars["SERVICE_ARTIFACT"],
                                                                       s_socket=config_vars["SERVICE_SOCKET"])

        # Service location wrapper
        nginx_services_conf += NGINX_SERVICE_BASE_TEMPLATE.format(base_url=config_vars["SERVICE_URL_BASE_PATH"],
                                                                  s_artifact=config_vars["SERVICE_ARTIFACT"])

        # Named location
        nginx_services_conf += (NGINX_SERVICE_WSGI_TEMPLATE if "wsgi" not in s or s["wsgi"]
                                else NGINX_SERVICE_NON_WSGI_TEMPLATE).format(s_artifact=config_vars["SERVICE_ARTIFACT"])

    return nginx_conf, nginx_upstreams_conf, nginx_services_conf


def main():
    args = sys.argv[1:]

    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} chord_services.json chord_services_config.json")
        exit(1)

    if os.environ.get("SINGULARITY_ENVIRONMENT", "") == "" and os.environ.get("CHORD_DOCKER_BUILD", "") == "":
        print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity or Docker container.")
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

        nginx_conf, nginx_upstreams_conf, nginx_services_conf = generate_nginx_confs(services, services_config_path)

        with open(NGINX_CONF_LOCATION, "w") as nf:
            nf.write(nginx_conf)

        with open(NGINX_UPSTREAMS_CONF_LOCATION, "w") as nf:
            nf.write(nginx_upstreams_conf)

        with open(NGINX_SERVICES_CONF_LOCATION, "w") as nf:
            nf.write(nginx_services_conf)


if __name__ == "__main__":
    main()
