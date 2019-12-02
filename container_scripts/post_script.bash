#!/usr/bin/env bash

CNODE="10.x"
CPG="11"

export DEBIAN_FRONTEND=noninteractive

# Make sure man folders are present (for Java and Postgres)
mkdir -p /usr/share/man/man1
mkdir -p /usr/share/man/man7

echo "[CHORD] Installing base dependencies from apt"

# Update APT
apt-get update > /dev/null

# Fix locale issues (Postgres seemed sensitive to this -- 2019-09-25)
apt-get install -y locales > /dev/null
sed -i 's/# en_US.UTF-8/en_US.UTF-8/g' /etc/locale.gen
locale-gen > /dev/null

export LANG="en_US.UTF-8"
export LC_CTYPE="en_US.UTF-8"

# Install shared build dependencies
apt-get full-upgrade -y > /dev/null
apt-get install -y -q nginx build-essential autoconf git curl libcurl4-openssl-dev libssl-dev > /dev/null

# Install Python 3.7
apt-get install -y python3 python3-pip python3-virtualenv > /dev/null

# Install Node.JS
curl -Ls https://deb.nodesource.com/setup_${CNODE} | bash - > /dev/null
apt-get install -y nodejs > /dev/null

###############################################################################
# Databases                                                                   #
###############################################################################

# Install Redis

echo "[CHORD] Installing Redis"

cd /chord || exit
echo "[CHORD]    Downloading"
curl -Lso redis-stable.tar.gz http://download.redis.io/redis-stable.tar.gz > /dev/null
echo "[CHORD]    Building"
tar -xzf redis-stable.tar.gz
cd redis-stable || exit
make > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
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

dbfilename redis.rdb
appendonly yes
appendfilename redis.aof

dir /chord/data/redis
EOC

# Install Postgres
# TODO: Use sd if we have cargo or if it's available in Debian in the future (thanks Romain)

echo "[CHORD] Installing Postgres"

apt-get install -y postgresql postgresql-contrib > /dev/null
sed -i "s=/var/lib/postgresql/${CPG}/main=/chord/data/postgresql=g" /etc/postgresql/${CPG}/main/postgresql.conf
sed -i "s=/var/run/postgresql/${CPG}-main.pid=/chord/tmp/postgresql/${CPG}-main.pid=g" \
  /etc/postgresql/${CPG}/main/postgresql.conf
sed -i 's/#listen_addresses = '\''localhost'\''/listen_addresses = '\'''\''/g' \
  /etc/postgresql/${CPG}/main/postgresql.conf
sed -i -r 's/port = [0-9]{4}/port = 5432/g' /etc/postgresql/${CPG}/main/postgresql.conf
sed -i 's,unix_socket_directories = '\''/var/run/postgresql'\'',unix_socket_directories = '\''/chord/tmp/postgresql'\'',g' \
  /etc/postgresql/${CPG}/main/postgresql.conf
sed -i 's/#unix_socket_permissions = 0777/unix_socket_permissions = 0770/g' /etc/postgresql/${CPG}/main/postgresql.conf

sed -i 's/ssl = on/ssl = off/g' /etc/postgresql/${CPG}/main/postgresql.conf

sed -i 's/#logging_collector = off/logging_collector = on/g' /etc/postgresql/${CPG}/main/postgresql.conf
sed -i 's,#log_directory = '\''pg_log'\'',log_directory = '\''/chord/tmp/postgresql/logs'\'',g' \
  /etc/postgresql/${CPG}/main/postgresql.conf
sed -i "s=/var/run/postgresql/${CPG}-main.pg_stat_tmp=/chord/tmp/postgresql/${CPG}-main.pg_stat_tmp=g" \
  /etc/postgresql/${CPG}/main/postgresql.conf

sed -i 's=postgres                                peer=postgres peer\nlocal all @/chord/tmp/.instance_user peer=g' \
  /etc/postgresql/${CPG}/main/pg_hba.conf
sed -i 's/all                                     peer/all                                     md5/g' \
  /etc/postgresql/${CPG}/main/pg_hba.conf

chmod o+r /etc/postgresql/${CPG}/main/pg_hba.conf  # TODO: Bad permissions, but this is default so it should be OK.

# Remove boot log for and link to future writeable location
rm -f /var/log/postgresql/postgresql-${CPG}-main.log
ln -s /chord/tmp/postgresql/postgresql-${CPG}-main.log /var/log/postgresql/postgresql-${CPG}-main.log


###############################################################################
# Biological Tools                                                            #
###############################################################################

echo "[CHORD] Installing HTSLib"

# Install HTSLib (may as well provide it, it'll likely be commonly used)
# TODO: Do we want to move this into pre_install for WES/variant/something, or no?
apt-get install -y zlib1g-dev libbz2-dev liblzma-dev > /dev/null
cd /chord || exit
echo "[CHORD]    Downloading"
curl -Lso htslib.tar.bz2 https://github.com/samtools/htslib/releases/download/1.9/htslib-1.9.tar.bz2 > /dev/null
tar -xjf htslib.tar.bz2
cd htslib-1.9 || exit
echo "[CHORD]    Building"
autoheader
autoconf
./configure > /dev/null
make > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
cd /chord || exit
rm htslib.tar.bz2
rm -r htslib-1.9

# Install bcftools
# TODO: Do we want to move this into pre_install for WES/variant/something, or no?
echo "[CHORD] Installing bcftools"
apt-get install -y bcftools > /dev/null

###############################################################################

export HOME="/chord"

# Install CHORD Web
echo "[CHORD] Installing chord_web"
cd /chord || exit
git clone --quiet --depth 1 https://bitbucket.org/genap/chord_web.git web
cd /chord/web || exit
NODE_ENV=development npm install > /dev/null
NODE_ENV=production npm run build > /dev/null
rm -r node_modules  # Don't need sources anymore after the bundle is built

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
echo "[CHORD] Installing common Python dependencies"
python3.7 -m pip install --no-cache-dir -r /chord/requirements.txt > /dev/null

# Run Python container setup script
echo "[CHORD] Setting up container"
cd /chord || exit
python3.7 ./container_scripts/container_setup.py \
  ./chord_services.json \
  ./chord_services_config.json

# Remove caches and build dependencies
rm -rf /chord/.cache
apt-get purge -y build-essential autoconf git curl python3-virtualenv > /dev/null
apt-get autoremove -y > /dev/null
apt-get clean > /dev/null
