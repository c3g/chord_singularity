#!/usr/bin/env bash

# Script to stop various processes for the CHORD system in order.

wait_for_kill () {
  while kill -0 "$1" 2> /dev/null; do
    sleep 0.5
  done
}

CPG="11"

# Kill the proxy first
killall nginx &> /dev/null

# Kill all services (gracefully-ish) to prevent them from trying to write to
# data storage systems (fs, Redis, Postgres.)

kill -2 "$(cat /chord/tmp/uwsgi/uwsgi.pid)" &> /dev/null
wait_for_kill "$(cat /chord/tmp/uwsgi/uwsgi.pid)"

chord_container_non_wsgi_stop \
  /chord/chord_services.json \
  /chord/chord_services_config.json

# Kill Redis
redis-cli -s /chord/tmp/redis.sock shutdown &> /dev/null

# Stop Postgres cluster
pg_ctlcluster ${CPG} main stop &> /dev/null

# Stop commands
chord_container_post_stop \
  /chord/chord_services.json \
  /chord/chord_services_config.json
sleep 2  # Wait for kills

# Remove any stray socket files
rm -f /chord/tmp/*.sock
