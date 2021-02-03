#!/usr/bin/env bash

# Script to (re-)generate a secure session secret for a Bento instance.
#  - must be called before NGINX is started
#  - the value should be copied into the NGINX conf template

openssl rand -hex 48
