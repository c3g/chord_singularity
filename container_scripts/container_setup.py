#!/usr/bin/env python3

import json
import os
import subprocess
import sys

from jsonschema import validate
from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import get_config_vars, TYPE_PYTHON, TYPE_JAVASCRIPT

# threads = 4 to allow some "parallel" requests; important for peer discovery/confirmation.
UWSGI_CONF_TEMPLATE = """[uwsgi]
vhost = true
manage-script-name = true
threads = 4
socket = {service_socket}
venv = {service_venv}
chdir = /chord/services/{service_artifact}
mount = /api/{service_artifact}={service_python_module}:{service_python_callable}
"""

NGINX_CONF_HEADER = """
daemon off;

worker_processes 1;
pid /chord/tmp/nginx.pid;

events {
  worker_connections 1024;
}

http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  
  client_body_temp_path /chord/tmp/nginx/client_tmp;
  proxy_temp_path /chord/tmp/nginx/proxy_tmp;
  fastcgi_temp_path /chord/tmp/nginx/fastcgi_tmp;
  uwsgi_temp_path /chord/tmp/nginx/uwsgi_tmp;
  scgi_temp_path /chord/tmp/nginx/scgi_tmp;

  sendfile off;
  keepalive_timeout 120;
  
  server_names_hash_bucket_size 128;

  index index.html index.htm;

"""

NGINX_CONF_SERVER_HEADER = """
  server {
    listen unix:/chord/tmp/nginx.sock;
    root /chord/web/public;
    index index.html index.htm index.nginx-debian.html;
    server_name _;
    
    location / {
      try_files $uri /index.html;
    }

    location /dist/ {
      alias /chord/web/dist/;
    }
"""

NGINX_CONF_FOOTER = """
  }
}
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
        nginx_conf += f"  upstream chord_{config_vars['SERVICE_ARTIFACT']} " \
                      f"{{ server unix:{config_vars['SERVICE_SOCKET']}; }}\n"

    nginx_conf += NGINX_CONF_SERVER_HEADER

    for s in services:
        config_vars = get_config_vars(s, services_config_path)
        base_url = config_vars['SERVICE_URL_BASE_PATH']

        s_artifact = config_vars['SERVICE_ARTIFACT']

        nginx_conf += f"    location = {base_url} {{ rewrite ^ {base_url}/; }}\n"
        nginx_conf += f"    location {base_url} {{ try_files $uri @{s_artifact}; }}\n"
        # nginx_conf += f"    location {base_url}/private {{ deny all; }}\n"  TODO: Figure this out

        if "wsgi" not in s or s["wsgi"]:
            nginx_conf += f"    location @{s_artifact} {{ " \
                          f"include uwsgi_params; uwsgi_pass chord_{s_artifact}; }}\n"

        else:
            nginx_conf += (
                f"    location @{s_artifact} {{ "
                f"proxy_http_version                 1.1; "
                f"proxy_pass_header                  Server; "
                f"proxy_set_header Upgrade           $http_upgrade; "
                f"proxy_set_header Connection        \"upgrade\"; "
                f"proxy_set_header Host              $http_host; "
                f"proxy_set_header X-Real-IP         $remote_addr; "
                f"proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for; "
                f"proxy_set_header X-Forwarded-Proto $scheme;"
                f"proxy_pass                         http://chord_{s_artifact}; "
                f"}}\n"
            )

        nginx_conf += "\n"

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

        with open("/etc/nginx/nginx.conf", "w") as nf:
            nf.write(generate_nginx_conf(services, services_config_path))


if __name__ == "__main__":
    main()
