#!/usr/bin/env bash

CPG="11"

source /chord/tmp/env

mkdir -p /chord/tmp/logs
mkdir -p /chord/tmp/data
mkdir -p /chord/tmp/postgresql/logs
mkdir -p /chord/tmp/uwsgi
mkdir -p /chord/tmp/nginx/client_tmp
mkdir -p /chord/tmp/nginx/proxy_tmp
mkdir -p /chord/tmp/nginx/fastcgi_tmp
mkdir -p /chord/tmp/nginx/uwsgi_tmp
mkdir -p /chord/tmp/nginx/scgi_tmp

cd /chord || exit

mkdir -p /chord/data/redis

echo "Starting Redis..."
nohup redis-server /etc/redis/redis.conf &> /dev/null  # Daemonized, so doesn't need &

mkdir -p /chord/data/postgresql

echo "Starting Postgres..."
# Initialize DB if nothing's there, then start the cluster
/usr/lib/postgresql/${CPG}/bin/initdb -D /chord/data/postgresql &> /dev/null
pg_ctlcluster ${CPG} main start

echo "Starting NGINX..."
nohup nginx &> /dev/null &

python3.7 ./container_scripts/container_pre_start.py ./chord_services.json ./chord_services_config.json

echo "Starting uWSGI..."
# TODO: Log to their own directories, not to uwsgi log
nohup uwsgi --emperor /chord/vassals --master --log-master --logto /chord/tmp/uwsgi/uwsgi.log &> /dev/null &

echo "Starting other services..."
python3.7 ./container_scripts/container_non_wsgi_start.py ./chord_services.json ./chord_services_config.json
