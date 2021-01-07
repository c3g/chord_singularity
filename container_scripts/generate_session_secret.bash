#!/usr/bin/env bash

# Script to (re-)generate a secure session secret for a Bento instance.
#  - must be called before NGINX is started
#  - the value in the file should be copied into the NGINX conf template

openssl rand -hex 48 > /chord/tmp/.session_secret
