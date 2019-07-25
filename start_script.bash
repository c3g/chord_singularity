#!/usr/bin/env bash

source /chord/tmp/env

mkdir -p /chord/tmp/logs
mkdir -p /chord/tmp/data
mkdir -p /chord/tmp/nginx/client_tmp
mkdir -p /chord/tmp/nginx/proxy_tmp
mkdir -p /chord/tmp/nginx/fastcgi_tmp
mkdir -p /chord/tmp/nginx/uwsgi_tmp
mkdir -p /chord/tmp/nginx/scgi_tmp

cd /chord || exit

python3.7 ./container_pre_start.py ./chord_services.json

echo "Starting NGINX..."
nohup nginx &
echo "Starting uWSGI..."
nohup uwsgi --emperor /chord/vassals --master &
