#!/usr/bin/env bash

echo "Starting NGINX..."
nohup nginx &
echo "Starting uWSGI..."
nohup uwsgi --emperor /chord/vassals --master &
