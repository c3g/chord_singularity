CPG="11"

# Kill the proxy first
killall nginx &> /dev/null

# Kill all services (gracefully-ish) to prevent them from trying to write to
# data storage systems (fs, Redis, Postgres.)
kill -2 "$(cat /chord/tmp/uwsgi/uwsgi.pid)" &> /dev/null
# TODO: Kill non-uWSGI services

# Kill Redis
redis-cli -s /chord/tmp/redis.sock shutdown &> /dev/null

# Stop Postgres cluster
pg_ctlcluster ${CPG} main stop &> /dev/null

# TODO: KILL COMMANDS ON SERVICES (TOIL RUNNER ETC.)
