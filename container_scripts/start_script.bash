#!/usr/bin/env bash

source /chord/tmp/env

mkdir -p /chord/tmp/logs
mkdir -p /chord/tmp/data
mkdir -p /chord/tmp/uwsgi
mkdir -p /chord/tmp/nginx/client_tmp
mkdir -p /chord/tmp/nginx/proxy_tmp
mkdir -p /chord/tmp/nginx/fastcgi_tmp
mkdir -p /chord/tmp/nginx/uwsgi_tmp
mkdir -p /chord/tmp/nginx/scgi_tmp

cd /chord || exit

python3.7 ./container_scripts/container_pre_start.py ./chord_services.json

echo "Starting Redis..."
nohup redis-server /etc/redis/redis.conf &> /dev/null  # Daemonized, so doesn't need &

echo "Starting NGINX..."
nohup nginx &> /dev/null &

echo "Starting uWSGI..."
# TODO: Log to their own directories, not to uwsgi log
nohup uwsgi --emperor /chord/vassals --master --log-master --logto /chord/tmp/uwsgi/uwsgi.log &> /dev/null &

echo "Starting other services..."
python3.7 ./container_scripts/container_non_wsgi_start.py ./chord_services.json
