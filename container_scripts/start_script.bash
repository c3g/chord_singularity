#!/usr/bin/env bash

CPG="11"

whoami > /chord/tmp/.instance_user

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

# Set up boot log in a writable location if it has not been set up already
if [[ ! -f /chord/tmp/postgresql/postgresql-${CPG}-main.log ]]; then
  touch /chord/tmp/postgresql/postgresql-${CPG}-main.log
fi

# Initialize DB if nothing's there, then start the cluster
database_created=False
if [[ ! "$(ls -A /chord/data/postgresql)" ]]; then
  /usr/lib/postgresql/${CPG}/bin/initdb -D /chord/data/postgresql &> /dev/null
  database_created=True
fi

pg_ctlcluster ${CPG} main start


echo "Starting NGINX..."
nohup nginx &> /dev/null &

NEW_DATABASE=$database_created python3.7 ./container_scripts/container_pre_start.py \
  ./chord_services.json \
  ./chord_services_config.json

echo "Starting uWSGI..."
# TODO: Log to their own directories, not to uwsgi log
nohup uwsgi \
 --emperor /chord/vassals \
 --master \
 --log-master \
 --logto /chord/tmp/uwsgi/uwsgi.log \
 --safe-pidfile /chord/tmp/uwsgi/uwsgi.pid \
 &> /dev/null &

echo "Starting other services..."
python3.7 ./container_scripts/container_non_wsgi_start.py \
  ./chord_services.json \
  ./chord_services_config.json
