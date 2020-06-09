#!/usr/bin/env bash

# Script to clone and/or update the Bento web interface
#  - Can only be called at runtime

# Load common runtime configuration
source /chord/data/.environment

# Clone the repository if it hasn't been done already
cd /chord/data || exit
if [[ ! -d /chord/data/web ]]; then
  git clone --quiet --depth 1 https://github.com/bento-platform/bento_web.git web
fi

# TODO: Specify version

# Update the repository if needed
cd /chord/data/web || exit
git pull --quiet

# Install dependencies and build the bundle
npm install > /dev/null
npm run build > /dev/null
