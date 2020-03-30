#!/usr/bin/env bash

# Script to start various processes for the CHORD system in order.

POSTGRES_VERSION="11"
REDIS_SOCKET="/chord/tmp/redis.sock"

# Remove any stray socket files
rm -f /chord/tmp/*.sock

whoami > /chord/tmp/.instance_user

mkdir -p /chord/tmp/logs
mkdir -p /chord/tmp/data
mkdir -p /chord/tmp/postgresql/logs
mkdir -p /chord/tmp/redis
mkdir -p /chord/tmp/uwsgi
mkdir -p /chord/tmp/nginx/client_tmp
mkdir -p /chord/tmp/nginx/proxy_tmp
mkdir -p /chord/tmp/nginx/fastcgi_tmp
mkdir -p /chord/tmp/nginx/uwsgi_tmp
mkdir -p /chord/tmp/nginx/scgi_tmp

cd /chord || exit

mkdir -p /chord/data/redis


echo "Starting Redis..."
nohup redis-server /etc/redis/redis.conf &> /chord/tmp/redis/redis.log  # Daemonized, so doesn't need &

# Wait for Redis to start
sleep 2
# Delete existing session locks in case they were persisted by accident
redis-cli -s "${REDIS_SOCKET}" --scan --pattern "oidc:*.lock" \
  | xargs -L 100 redis-cli -s "${REDIS_SOCKET}" "DEL"

mkdir -p /chord/data/postgresql


echo "Starting Postgres..."

# Set up boot log in a writable location if it has not been set up already
if [[ ! -f /chord/tmp/postgresql/postgresql-${POSTGRES_VERSION}-main.log ]]; then
  touch /chord/tmp/postgresql/postgresql-${POSTGRES_VERSION}-main.log
fi

# Initialize DB if nothing's there
database_created=False
if [[ ! "$(ls -A /chord/data/postgresql)" ]]; then
  /usr/lib/postgresql/${POSTGRES_VERSION}/bin/initdb -D /chord/data/postgresql &> /dev/null
  database_created=True
fi

# Start the Postges cluster
pg_ctlcluster ${POSTGRES_VERSION} main start


echo "Running pre-start operations..."
NEW_DATABASE=$database_created chord_container_pre_start

# Load common runtime configuration
source /chord/data/.environment

echo "Starting uWSGI..."
nohup uwsgi \
 --emperor /chord/vassals \
 --master \
 --safe-pidfile /chord/tmp/uwsgi/uwsgi.pid \
 &> /dev/null &

echo "Starting other services..."
chord_container_non_wsgi_start

echo "Installing chord_web..."

cd /chord/data || exit
if [[ ! -d /chord/data/web ]]; then
  git clone --quiet --depth 1 https://github.com/c3g/chord_web.git web
fi
# TODO: Specify version
cd /chord/data/web || exit
git pull --quiet

npm install > /dev/null
npm run build > /dev/null

echo "Starting OpenResty NGINX..."
export PATH=/usr/local/openresty/bin:/usr/local/openresty/nginx/sbin:$PATH
nohup nginx &> /dev/null &

# Wait for NGINX to start before running post-start hooks
sleep 1

echo "Running post-start operations..."
chord_container_post_start
