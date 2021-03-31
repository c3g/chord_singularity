#!/usr/bin/env python3

import os
import subprocess
import sys

from .chord_common import (
    AUTH_CONFIG_PATH,
    INSTANCE_CONFIG_PATH,
    TYPE_PYTHON,
    TYPE_JAVASCRIPT,
    ServiceList,
    get_config_vars,
    ContainerJob,
)

# threads = 4 to allow some "parallel" requests; important for peer discovery/confirmation.
UWSGI_CONF_TEMPLATE = """[uwsgi]
vhost = true
manage-script-name = true
enable-threads = true
socket-timeout = 600
harakiri = 610
lazy-apps = true  # use pre-forking instead, to prevent threading headaches
buffer-size = 32768  # allow reading of larger headers, for e.g. auth
socket = {SERVICE_SOCKET}
venv = {SERVICE_VENV}
chdir = /chord/services/{SERVICE_ARTIFACT}
mount = /api/{SERVICE_ARTIFACT}={service_python_module}:{service_python_callable}
vacuum = true
logto = {SERVICE_LOGS}/{SERVICE_ARTIFACT}.log
# To solve an issue between werkzeug, uWSGI and reading from a file pointer
wsgi-disable-file-wrapper = true
{service_python_args}
# Import configuration environment variables into uWSGI environment
for-readline = {SERVICE_ENVIRONMENT}
  env = %(_)
endfor =
{service_run_environment}
"""

NGINX_CONF_LOCATION = "/usr/local/openresty/nginx/conf/nginx.conf"
NGINX_UPSTREAMS_CONF_LOCATION = "/usr/local/openresty/nginx/conf/chord_upstreams.conf"
NGINX_GATEWAY_CONF_TPL_LOCATION = "/usr/local/openresty/nginx/conf/nginx_gateway.conf.template"
NGINX_GATEWAY_CONF_LOCATION = "/chord/tmp/nginx_gateway.conf"
NGINX_SERVICES_CONF_LOCATION = "/usr/local/openresty/nginx/conf/chord_services.conf"

NGINX_GATEWAY_CONF_TPL_TEMPLATE = """
limit_req_zone $binary_remote_addr zone=external:10m rate=10r/s;

server {{
  listen LISTEN_ON;  # unix:/chord/tmp/nginx.sock;
  root /chord/data/web/dist;
  server_name _;

  # Enable to show debugging information in the error log:
  # error_log /usr/local/openresty/nginx/logs/error.log debug;

  # lua-resty-session configuration
  
  # - TODO
  set $session_name bento_session;

  #  - cookie stuff:
  set $session_cookie_lifetime 180s;
  set $session_cookie_renew    180s;

  #  - use Redis for sessions to allow scaling of NGINX:
  set $session_storage         redis;
  set $session_redis_prefix    oidc;
  set $session_redis_socket    unix:///chord/tmp/redis.sock;
  set $session_redis_uselocking off;  # TODO: DO WE WANT THIS

  # - template value, replaced at startup using sed:
  set $session_secret          "SESSION_SECRET";
  
  # - Per lua-resty-session, the 'regenerate' strategy is more reliable for
  #   SPAs which make a lot of asynchronous requests, as it does not 
  #   immediately replace the old records for sessions when making a new one.
  set $session_strategy        regenerate;

  # CHORD constants (configuration file locations)
  set $chord_auth_config     "{auth_config}";
  set $chord_instance_config "{instance_config}";

  # Head off any favicon requests before they pass through the auth flow
  location = /favicon.ico {{
    return 404;
    log_not_found off;
    access_log off;
  }}

  # Serve up public files before they pass through the auth flow
  location /public/ {{
    alias /chord/data/web/public/;
  }}

  # For the next few blocks, set up two-stage rate limiting:
  #   Store:  10 MB worth of IP addresses (~160 000)
  #   Rate:   10 requests per second.
  #   Bursts: Allow for bursts of 15 with no delay and an additional 25
  #          (total 40) queued requests before throwing up 503.
  #   This limit is for requests from outside the DMZ; internal microservices
  #   currently get unlimited access.
  # See: https://www.nginx.com/blog/rate-limiting-nginx/

  location / {{
    limit_req zone=external burst=40 delay=15;
    access_by_lua_file /chord/container_scripts/proxy_auth.lua;
    try_files $uri /index.html;
  }}

  location = /api/node-info {{
    limit_req zone=external burst=40 delay=15;
    content_by_lua_file /chord/container_scripts/node_info.lua;
  }}

  location /api/ {{
    limit_req zone=external burst=40 delay=15;
    access_by_lua_file   /chord/container_scripts/proxy_auth.lua;

    # TODO: Deduplicate with below?

    proxy_http_version   1.1;

    proxy_pass_header    Server;
    proxy_set_header     Upgrade           $http_upgrade;
    proxy_set_header     Connection        "upgrade";
    proxy_set_header     Host              $http_host;
    proxy_set_header     X-Real-IP         $remote_addr;
    proxy_set_header     X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header     X-Forwarded-Proto $http_x_forwarded_proto;

    # Clear X-CHORD-Internal header and set it to the "off" value (0)
    proxy_set_header     X-CHORD-Internal  "0";

    proxy_pass           http://unix:/chord/tmp/nginx_internal.sock;

    client_body_timeout  660s;
    proxy_read_timeout   660s;
    proxy_send_timeout   660s;
    send_timeout         660s;

    client_max_body_size 200m;
  }}
}}
"""

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
  keepalive_timeout 660;

  server_names_hash_bucket_size 128;

  # Disable server_tokens for security reasons
  server_tokens off;

  index index.html index.htm;

  # lua-resty-openidc global configuration
  # ======================================

  resolver 8.8.8.8;  # resolve OIDC URLs with Google DNS

  # Force Lua code cache to be on for session secret preservation and
  # performance reasons:
  lua_code_cache on;  

  lua_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
  lua_ssl_verify_depth 5;
  lua_shared_dict discovery 1m;
  lua_shared_dict jwks 1m;
  lua_shared_dict introspection 2m;

  # ======================================

  # Explicitly prevent underscores in headers from being passed, even though
  # off is the default. This prevents auth header forging.
  # e.g. https://docs.djangoproject.com/en/3.0/howto/auth-remote-user/
  underscores_in_headers off;

  # Prevent proxy from trying multiple upstreams.
  proxy_next_upstream off;

  include {upstreams_conf};

  include {gateway_conf};

  server {{
    listen unix:/chord/tmp/nginx_internal.sock;
    root /chord/data/web/dist;  # Leave this here so the server has a root (unused)
    server_name '';

    access_by_lua_block {{
      if ngx.ctx.chord_internal == nil then
        -- Need to set CHORD internal status, since we're at the start of the request
        if ngx.var.http_x_chord_internal == nil then
          ngx.ctx.chord_internal = '1'
        else
          ngx.ctx.chord_internal = '0'
        end
      end
      ngx.req.set_header('X-CHORD-Internal', ngx.ctx.chord_internal)
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
"""

NGINX_SERVICE_WSGI_TEMPLATE = """
location {base_url} {{
  include              uwsgi_params;
  # uwsgi_param          HTTP_Host            $http_host;
  # uwsgi_param          HTTP_X-Forwarded-For $proxy_add_x_forwarded_for;
  uwsgi_pass           chord_{s_artifact};
  uwsgi_read_timeout   630s;
  uwsgi_send_timeout   630s;

  client_body_timeout  630s;
  client_max_body_size 200m;
  send_timeout         630s;
}}
"""

NGINX_SERVICE_NON_WSGI_TEMPLATE = """
location {base_url} {{
  proxy_http_version   1.1;

  proxy_pass_header    Server;
  proxy_set_header     Upgrade           $http_upgrade;
  proxy_set_header     Connection        "upgrade";
  proxy_pass_header    Host;
  proxy_pass_header    X-Real-IP;
  proxy_set_header     X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_pass_header    X-Forwarded-Proto;
  proxy_pass_header    X-CHORD-Internal;  # Pass any internal-authorized accesses along

  proxy_pass           http://chord_{s_artifact};

  proxy_read_timeout   630s;
  proxy_send_timeout   630s;

  client_body_timeout  630s;
  client_max_body_size 200m;
  send_timeout         630s;
}}
"""


def install_apt_dependencies(services: ServiceList):
    apt_dependencies = set().union(*(s.get("apt_dependencies", ()) for s in services))
    subprocess.run(("apt-get", "install", "-y", *apt_dependencies), stdout=subprocess.DEVNULL, check=True)


def run_pre_install_commands(services: ServiceList):
    for s in services:
        for c in s.get("pre_install_commands", ()):
            print("[CHORD Container Setup]    {}".format(c))
            subprocess.run(c, shell=True, check=True, stdout=subprocess.DEVNULL)


def create_service_virtual_environments(services: ServiceList):
    for s in services:
        s_language = s["type"]["language"]
        s_artifact = s["type"]["artifact"]
        s_repo = s["repository"]

        subprocess.run(f"/bin/bash -c 'mkdir -p /chord/services/{s_artifact}'", shell=True, check=True)

        if s_language == TYPE_PYTHON:
            subprocess.run(
                f"/bin/bash -c 'cd /chord/services/{s_artifact}; "
                f"              python3.7 -m virtualenv --system-site-packages -p python3.7 env; "
                f"              source env/bin/activate; "
                f"              pip install --no-cache-dir git+{s_repo};"
                f"              deactivate'",
                shell=True,
                check=True,
                stdout=subprocess.DEVNULL
            )

        elif s_language == TYPE_JAVASCRIPT:
            subprocess.run(
                f"/bin/bash -c 'cd /chord/services/{s_artifact}; "
                f"              npm install -g {s_repo}'",
                shell=True,
                check=True,
                stdout=subprocess.DEVNULL
            )

        else:
            raise NotImplementedError(f"Unknown language: {s_language}")


def _generate_uwsgi_confs(services: ServiceList):
    for s in services:
        if not s.get("wsgi", True):
            continue

        config_vars = get_config_vars(s)
        yield (s, UWSGI_CONF_TEMPLATE.format(
            **config_vars,
            service_python_module=s["python_module"],
            service_python_callable=s["python_callable"],
            service_python_args=(f"pyargv = {' '.join(a.format(**config_vars) for a in s['python_args'])}"
                                 if "python_args" in s else ""),
            service_run_environment="\n".join(f"env = {e}={val.format(**config_vars)}"
                                              for e, val in s.get("run_environment", {}).items())
        ))


def write_uwsgi_confs(services: ServiceList):
    for s, c in _generate_uwsgi_confs(services):
        conf_path = f"/chord/vassals/{s['type']['artifact']}.ini"  # TODO: Make this a config var / template

        if os.path.exists(conf_path):
            print(f"Error: File already exists: '{conf_path}'", file=sys.stderr)
            exit(1)

        with open(conf_path, "w") as uf:
            uf.write(c)


def write_nginx_confs(services: ServiceList):
    nginx_conf = NGINX_CONF_TEMPLATE.format(
        upstreams_conf=NGINX_UPSTREAMS_CONF_LOCATION,
        gateway_conf=NGINX_GATEWAY_CONF_LOCATION,
        services_conf=NGINX_SERVICES_CONF_LOCATION,
    )
    nginx_gateway_conf_tpl = NGINX_GATEWAY_CONF_TPL_TEMPLATE.format(
        auth_config=AUTH_CONFIG_PATH,
        instance_config=INSTANCE_CONFIG_PATH,
    )
    nginx_upstreams_conf = ""
    nginx_services_conf = ""

    for s in services:
        config_vars = get_config_vars(s)

        # Upstream
        nginx_upstreams_conf += NGINX_SERVICE_UPSTREAM_TEMPLATE.format(s_artifact=config_vars["SERVICE_ARTIFACT"],
                                                                       s_socket=config_vars["SERVICE_SOCKET"])

        # Service location wrapper
        nginx_services_conf += NGINX_SERVICE_BASE_TEMPLATE.format(base_url=config_vars["SERVICE_URL_BASE_PATH"],
                                                                  s_artifact=config_vars["SERVICE_ARTIFACT"])

        # Named location
        nginx_services_conf += (NGINX_SERVICE_WSGI_TEMPLATE if "wsgi" not in s or s["wsgi"]
                                else NGINX_SERVICE_NON_WSGI_TEMPLATE).format(
            base_url=config_vars["SERVICE_URL_BASE_PATH"], s_artifact=config_vars["SERVICE_ARTIFACT"])

    # Write configurations to the container file system

    with open(NGINX_CONF_LOCATION, "w") as nf:
        nf.write(nginx_conf)

    with open(NGINX_GATEWAY_CONF_TPL_LOCATION, "w") as nf:
        nf.write(nginx_gateway_conf_tpl)

    with open(NGINX_UPSTREAMS_CONF_LOCATION, "w") as nf:
        nf.write(nginx_upstreams_conf)

    with open(NGINX_SERVICES_CONF_LOCATION, "w") as nf:
        nf.write(nginx_services_conf)


class ContainerSetupJob(ContainerJob):
    def job(self, services: ServiceList):
        # STEP 1: Install de-duplicated apt dependencies.
        print("[CHORD Container Setup] Installing apt dependencies...")
        install_apt_dependencies(services)

        # STEP 2: Run pre-install commands
        print("[CHORD Container Setup] Running service pre-install commands...")
        run_pre_install_commands(services)

        # STEP 3: Create virtual environments and install packages
        print("[CHORD Container Setup] Creating virtual environments...")
        create_service_virtual_environments(services)

        # STEP 4: Generate uWSGI configuration files
        print("[CHORD Container Setup] Generating uWSGI configuration files...")
        write_uwsgi_confs(services)

        # STEP 5: Generate NGINX configuration file
        print("[CHORD Container Setup] Generating NGINX configuration file...")
        write_nginx_confs(services)


job = ContainerSetupJob(build=True)

if __name__ == "__main__":
    job.main()
