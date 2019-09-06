#!/usr/bin/env bash

# Update and install shared build dependencies
apt update
apt full-upgrade -y
apt install -y nginx build-essential git curl

# Install Node.JS
curl -sL https://deb.nodesource.com/setup_10.x | bash -
apt install -y nodejs

# Install Redis
cd /chord || exit
curl -o redis-stable.tar.gz http://download.redis.io/redis-stable.tar.gz
tar -xzf redis-stable.tar.gz
cd redis-stable || exit
make
make install
cd /chord || exit
rm redis-stable.tar.gz
rm -r redis-stable
mkdir -p /etc/redis
# TODO: SECURITY: Make sure redis isn't exposed publically in any way
cat > /etc/redis/redis.conf <<- EOC
# Don't bind a port, listen on localhost
port 0
bind 127.0.0.1

# Use a unix socket for communications
unixsocket /chord/tmp/redis.sock
unixsocketperm 770

pidfile /chord/tmp/redis.pid

daemonize yes
EOC

# Download WOM tool
# TODO: This should be a hook in WES
curl -o /chord/womtool.jar https://github.com/broadinstitute/cromwell/releases/download/45.1/womtool-45.1.jar

export HOME="/chord"

# Install CHORD Web
cd /chord || exit
git clone --depth 1 https://bitbucket.org/genap/chord_web.git web
cd /chord/web || exit
NODE_ENV=development npm install
NODE_ENV=production npm run build

# Create CHORD folder structure
mkdir -p /chord/data
mkdir -p /chord/tmp/nginx
mkdir /chord/services
mkdir /chord/vassals

# Set up NGINX logging
rm /var/log/nginx/*.log
touch /chord/tmp/nginx/access.log
touch /chord/tmp/nginx/error.log
ln -s /chord/tmp/nginx/access.log /var/log/nginx/access.log
ln -s /chord/tmp/nginx/error.log /var/log/nginx/error.log

# Install common Python dependencies
python3.7 -m pip install --no-cache-dir virtualenv
python3.7 -m pip install --no-cache-dir -r /chord/requirements.txt

# Run Python container setup script
cd /chord || exit
python3.7 ./container_scripts/container_setup.py ./chord_services.json

# Remove caches and build dependencies
rm -rf /chord/.cache
apt purge -y build-essential git curl
apt autoremove -y
apt clean
