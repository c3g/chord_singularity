#!/usr/bin/env bash

# Script to install components of CHORD into a Singularity container.

CPU_COUNT=$(grep -c "^processor" /proc/cpuinfo)

echo "[CHORD] Using ${CPU_COUNT} cores for compilations"

OPENRESTY_VERSION="1.17.8.2"
NODE_VERSION="12.x"
POSTGRES_VERSION="11"
HTSLIB_VERSION="1.10"
BCFTOOLS_VERSION="1.10"

# Avoid warnings about non-interactive shell
export DEBIAN_FRONTEND=noninteractive

# Avoid warnings about parsing apt keys due to stdout redirection
export APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=true

# Make sure man folders are present (for Java and Postgres)
mkdir -p /usr/share/man/man1
mkdir -p /usr/share/man/man7

echo "[CHORD] Installing apt-sourced shared dependencies"

# Update APT
apt-get update > /dev/null

# Install apt-utils and suppress the "no apt-utils" warning here
apt-get install -y --no-install-recommends apt-utils > /dev/null 2>&1

# Fix locale issues (Postgres seemed sensitive to this -- 2019-09-25)
apt-get install -y locales > /dev/null
sed -i 's/# en_US.UTF-8/en_US.UTF-8/g' /etc/locale.gen
locale-gen > /dev/null

export LANG="en_US.UTF-8"
export LC_CTYPE="en_US.UTF-8"

# Install:
#   - shared build dependencies
#   - Python 3.7
apt-get full-upgrade -y > /dev/null
apt-get install -y -q \
 build-essential \
 autoconf \
 git \
 curl \
 libcurl4-openssl-dev \
 libpcre3-dev \
 libssl-dev \
 zlib1g-dev \
 python3 \
 python3-pip \
 python3-virtualenv \
 > /dev/null

# Install Node.JS
curl -Ls "https://deb.nodesource.com/setup_${NODE_VERSION}" | bash - > /dev/null
apt-get install -y nodejs > /dev/null

###############################################################################
# OIDC NGINX Setup                                                            #
###############################################################################

echo "[CHORD] Installing OpenResty v${OPENRESTY_VERSION}"

cd /chord || exit
echo "[CHORD]    Downloading"
curl -Lso openresty.tar.gz "https://openresty.org/download/openresty-${OPENRESTY_VERSION}.tar.gz" > /dev/null
echo "[CHORD]    Building"
tar -xzf openresty.tar.gz
cd "openresty-${OPENRESTY_VERSION}" || exit
# To compile NGINX with debug info, use --with-debug
./configure --with-pcre-jit --with-ipv6 > /dev/null
make "-j${CPU_COUNT}" > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
cd /chord || exit
rm openresty.tar.gz
rm -r "openresty-${OPENRESTY_VERSION}"
echo "[CHORD]    Setting up"
# This export will only last until the end of setup
export PATH=/usr/local/openresty/bin:/usr/local/openresty/nginx/sbin:$PATH
# Set up NGINX logging
mkdir -p /chord/tmp/nginx
touch /chord/tmp/nginx/access.log
touch /chord/tmp/nginx/error.log
ln -s /chord/tmp/nginx/access.log /usr/local/openresty/nginx/logs/access.log
ln -s /chord/tmp/nginx/error.log /usr/local/openresty/nginx/logs/error.log

echo "[CHORD] Installing OpenResty modules"
opm install zmartzone/lua-resty-openidc > /dev/null 2>&1


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
make "-j${CPU_COUNT}" > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
cd /chord || exit
rm redis-stable.tar.gz
rm -r redis-stable
echo "[CHORD]    Setting up"
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

echo "[CHORD] Installing Postgres v${POSTGRES_VERSION}"

POSTGRES_CONF="/etc/postgresql/${POSTGRES_VERSION}/main/postgresql.conf"
POSTGRES_HBA_CONF="/etc/postgresql/${POSTGRES_VERSION}/main/pg_hba.conf"

apt-get install -y postgresql postgresql-contrib > /dev/null
sed -i "s=/var/lib/postgresql/${POSTGRES_VERSION}/main=/chord/data/postgresql=g" $POSTGRES_CONF
sed -i "s=/var/run/postgresql/${POSTGRES_VERSION}-main.pid=/chord/tmp/postgresql/${POSTGRES_VERSION}-main.pid=g" \
  $POSTGRES_CONF
sed -i 's/#listen_addresses = '\''localhost'\''/listen_addresses = '\'''\''/g' $POSTGRES_CONF
sed -i -r 's/port = [0-9]{4}/port = 5432/g' $POSTGRES_CONF
sed -i 's,unix_socket_directories = '\''/var/run/postgresql'\'',unix_socket_directories = '\''/chord/tmp/postgresql'\'',g' \
  $POSTGRES_CONF
sed -i 's/#unix_socket_permissions = 0777/unix_socket_permissions = 0770/g' $POSTGRES_CONF

sed -i 's/ssl = on/ssl = off/g' $POSTGRES_CONF

sed -i 's/#logging_collector = off/logging_collector = on/g' $POSTGRES_CONF
sed -i 's,#log_directory = '\''pg_log'\'',log_directory = '\''/chord/tmp/postgresql/logs'\'',g' $POSTGRES_CONF
sed -i "s=/var/run/postgresql/${POSTGRES_VERSION}-main.pg_stat_tmp=/chord/tmp/postgresql/${POSTGRES_VERSION}-main.pg_stat_tmp=g" \
  $POSTGRES_CONF

sed -i 's=postgres                                peer=postgres peer\nlocal all @/chord/tmp/.instance_user peer=g' \
  $POSTGRES_HBA_CONF
sed -i 's/all                                     peer/all                                     md5/g' \
  $POSTGRES_HBA_CONF

chmod o+r $POSTGRES_HBA_CONF  # TODO: Bad permissions, but this is default so it should be OK.

# Remove boot log for and link to future writeable location
rm -f "/var/log/postgresql/postgresql-${POSTGRES_VERSION}-main.log"
ln -s "/chord/tmp/postgresql/postgresql-${POSTGRES_VERSION}-main.log" \
  "/var/log/postgresql/postgresql-${POSTGRES_VERSION}-main.log"


###############################################################################
# Biological Tools                                                            #
###############################################################################

# Install HTSLib (may as well provide it, it'll likely be commonly used)
# TODO: Do we even need this?
echo "[CHORD] Installing HTSLib v${HTSLIB_VERSION}"
# TODO: Do we want to move this into pre_install for WES/variant/something, or no?
apt-get install -y zlib1g-dev libbz2-dev liblzma-dev > /dev/null
cd /chord || exit
echo "[CHORD]    Downloading"
curl -Lso htslib.tar.bz2 \
  "https://github.com/samtools/htslib/releases/download/${HTSLIB_VERSION}/htslib-${HTSLIB_VERSION}.tar.bz2" > /dev/null
tar -xjf htslib.tar.bz2
cd "htslib-${HTSLIB_VERSION}" || exit
echo "[CHORD]    Building"
autoheader
autoconf
./configure > /dev/null
make "-j${CPU_COUNT}" > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
cd /chord || exit
rm htslib.tar.bz2
rm -r "htslib-${HTSLIB_VERSION}"

# Install bcftools
echo "[CHORD] Installing bcftools v${BCFTOOLS_VERSION}"
cd /chord || exit
echo "[CHORD]    Downloading"
curl -Lso bcftools.tar.bz2 \
  "https://github.com/samtools/bcftools/releases/download/${BCFTOOLS_VERSION}/bcftools-${BCFTOOLS_VERSION}.tar.bz2" \
  > /dev/null
tar -xjf bcftools.tar.bz2
cd "bcftools-${BCFTOOLS_VERSION}" || exit
echo "[CHORD]    Building"
autoheader
autoconf
./configure > /dev/null
make "-j${CPU_COUNT}" > /dev/null
echo "[CHORD]    Installing"
make install > /dev/null
echo "[CHORD]    Cleaning up"
cd /chord || exit
rm bcftools.tar.bz2
rm -r "bcftools-${BCFTOOLS_VERSION}"


###############################################################################

export HOME="/chord"

# Create CHORD folder structure
mkdir -p /chord/data
mkdir /chord/services
mkdir /chord/vassals

# Install chord_container_tools
echo "[CHORD] Installing chord_container_tools Python package"
python3.7 -m pip install --no-cache-dir /chord/chord_container_tools > /dev/null

# Run Python container setup script
echo "[CHORD] Setting up container"
cd /chord || exit
chord_container_setup

# Remove caches and build dependencies
rm -rf /chord/.cache
apt-get purge -y build-essential autoconf python3-virtualenv > /dev/null
apt-get autoremove -y > /dev/null
apt-get clean > /dev/null
