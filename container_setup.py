#!/usr/bin/env python3

import json
import os
import subprocess
import sys

from jsonschema import validate

NGINX_CONF_HEADER = """
daemon off;

user www-data;
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

  server {
    listen 80;
    root /var/www/html;
    index index.html index.htm index.nginx-debian.html;
    server_name _;
    
"""

NGINX_CONF_FOOTER = """
  }
}
"""


def generate_uwsgi_confs(services):
    uwsgi_confs = []

    for s in services:
        uwsgi_conf = "[uwsgi]\n"
        uwsgi_conf += "vhost = true\n"
        uwsgi_conf += f"socket = /chord/tmp/{s['id']}.sock\n"
        uwsgi_conf += f"venv = /chord/services/{s['id']}/env\n"
        uwsgi_conf += f"chdir = /chord/services/{s['id']}\n"
        uwsgi_conf += f"module = {s['python_module']}\n"
        uwsgi_conf += f"callable = {s['python_callable']}\n"
        uwsgi_conf += f"mount = /{s['id']}={s['python_module']}:{s['python_callable']}\n"
        uwsgi_conf += f"pyargv = {' '.join([a.format(CHORD_TMP='/chord/tmp') for a in s['python_args']])}\n"

        uwsgi_confs.append(uwsgi_conf)

    return uwsgi_confs


def generate_nginx_conf(services):
    nginx_conf = NGINX_CONF_HEADER

    for s in services:
        nginx_conf += f"    location = /{s['id']} {{ rewrite ^ /{s['id']}/; }}\n"
        nginx_conf += f"    location /{s['id']} {{ try_files $uri @{s['id']}; }}\n"
        nginx_conf += f"    location @{s['id']} {{ include uwsgi_params; " \
            f"uwsgi_pass unix:/chord/tmp/{s['id']}.sock; }}\n"

    nginx_conf += NGINX_CONF_FOOTER

    return nginx_conf


def main():
    args = sys.argv[1:]

    if len(args) != 1:
        print(f"Usage: {sys.argv[0]} chord_services.json")
        exit(1)

    if os.environ.get("SINGULARITY_ENVIRONMENT", "") == "":
        print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity container.")
        exit(1)

    with open("./chord_services.schema.json") as cf, open(args[0], "r") as sf:
        schema = json.load(cf)
        services = json.load(sf)

        validate(instance=services, schema=schema)

        # STEP 1: Install deduplicated apt dependencies.

        print("[CHORD] Installing apt dependencies...")

        apt_dependencies = set()
        for s in services:
            apt_dependencies = apt_dependencies.union(s["apt_dependencies"])

        subprocess.run(["apt", "install", "-y"] + list(apt_dependencies), check=True)

        # STEP 2: Fetch services

        print("[CHORD] Fetching services...")

        # TODO: CHECKOUT SPECIFIC TAGS

        os.chdir("/chord/services")

        for s in services:
            subprocess.run(["git", "clone", s["repository"], s["id"]], check=True)  # Clone as a specific name
            os.chdir(f"/chord/services/{s['id']}")

        os.chdir("/chord")

        # STEP 3: Create virtual environments and install packages

        print("[CHORD] Creating virtual environments...")

        for s in services:
            subprocess.run(
                f"/bin/bash -c 'virtualenv env;"
                f"              cd /chord/services/{s['id']}; "
                f"              virtualenv env; "
                f"              source env/bin/activate; "
                f"              pip install -r requirements.txt; "
                f"              python setup.py install; "
                f"              deactivate'",
                shell=True,
                check=True
            )

        os.chdir("/chord")

        # STEP 4: Generate uWSGI configuration files

        print("[CHORD] Generating uWSGI configuration files...")

        for s, c in zip(services, generate_uwsgi_confs(services)):
            conf_path = f"/chord/vassals/{s['id']}.ini"

            if os.path.exists(conf_path):
                print(f"Error: File already exists: '{conf_path}'")
                exit(1)

            with open(conf_path, "w") as uf:
                uf.write(c)

        # STEP 5: Generate NGINX configuration file

        print("[CHORD] Generating NGINX configuration file...")

        with open("/etc/nginx/nginx.conf", "w") as nf:
            nf.write(generate_nginx_conf(services))

        # TODO: Start script hooks for services
        # TODO: Persistent data directory binding


if __name__ == "__main__":
    main()
