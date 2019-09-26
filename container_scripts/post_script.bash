#!/usr/bin/env bash

export DEBIAN_FRONTEND=noninteractive

# Make sure man folders are present (for Java and Postgres)
mkdir -p /usr/share/man/man1
mkdir -p /usr/share/man/man7

# Update APT
apt update

# Fix locale issues (Postgres seemed sensitive to this -- 2019-09-25)
apt install -y locales
sed -i 's/# en_US.UTF-8/en_US.UTF-8/g' /etc/locale.gen
locale-gen

export LANG="en_US.UTF-8"
export LC_CTYPE="en_US.UTF-8"

# Install shared build dependencies
apt full-upgrade -y
apt install -y nginx build-essential autoconf git curl

# Install Node.JS
curl -sL https://deb.nodesource.com/setup_10.x | bash -
apt install -y nodejs

###############################################################################
# Databases                                                                   #
###############################################################################

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

dbfilename redis.rdb
dir /chord/data/redis
EOC

# Install Postgres
# TODO: Use sd if we have cargo or if it's available in Debian in the future (thanks Romain)

apt install -y postgresql postgresql-contrib
sed -i 's=/var/lib/postgresql/9.6/main=/chord/data/postgresql=g' /etc/postgresql/9.6/main/postgresql.conf
sed -i 's=/var/run/postgresql/9.6-main.pid=/chord/tmp/postgresql/9.6-main.pid=g' \
  /etc/postgresql/9.6/main/postgresql.conf
sed -i 's/#listen_addresses = '\''localhost'\''/listen_addresses = '\'''\''/g' /etc/postgresql/9.6/main/postgresql.conf
sed -i -r 's/port = [0-9]{4}/port = 5433/g' /etc/postgresql/9.6/main/postgresql.conf
sed -i 's,unix_socket_directories = '\''/var/run/postgresql'\'',unix_socket_directories = '\''/chord/tmp/postgresql'\'',g' \
  /etc/postgresql/9.6/main/postgresql.conf
sed -i 's/#unix_socket_permissions = 0777/unix_socket_permissions = 0770/g' /etc/postgresql/9.6/main/postgresql.conf

sed -i 's/ssl = true/ssl = false/g' /etc/postgresql/9.6/main/postgresql.conf

sed -i 's/#logging_collector = off/logging_collector = on/g' /etc/postgresql/9.6/main/postgresql.conf
sed -i 's,#log_directory = '\''pg_log'\'',log_directory = '\''/chord/tmp/postgresql/logs'\'',g' \
  /etc/postgresql/9.6/main/postgresql.conf
sed -i 's=/var/run/postgresql/9.6-main.pg_stat_tmp=/chord/tmp/postgresql/9.6-main.pg_stat_tmp=g' \
  /etc/postgresql/9.6/main/postgresql.conf

sed -i 's,pg_ctl_options = '\'''\'',pg_ctl_options = '\''-l /chord/tmp/postgresql/postgresql-9.6-main.log'\'',g' \
  /etc/postgresql/9.6/main/pg_ctl.conf

sed -i 's/all                                     peer/all                                     trust/g' \
  /etc/postgresql/9.6/main/pg_hba.conf

chmod o+r /etc/postgresql/9.6/main/pg_hba.conf  # TODO: Bad permissions, but this is default so it should be OK.


###############################################################################
# Biological Tools                                                            #
###############################################################################

# Install HTSLib (may as well provide it, it'll likely be commonly used)
# TODO: Do we want to move this into pre_install for WES/variant/something, or no?
apt install -y zlib1g-dev libbz2-dev liblzma-dev
cd /chord || exit
curl -Lo htslib.tar.bz2 https://github.com/samtools/htslib/releases/download/1.9/htslib-1.9.tar.bz2
tar -xjf htslib.tar.bz2
cd htslib-1.9 || exit
autoheader
autoconf
./configure
make
make install
cd /chord || exit
rm htslib.tar.bz2
rm -r htslib-1.9

# Install bcftools
# TODO: Do we want to move this into pre_install for WES/variant/something, or no?
apt install -y bcftools

###############################################################################

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
apt purge -y build-essential autoconf git curl
apt autoremove -y
apt clean
