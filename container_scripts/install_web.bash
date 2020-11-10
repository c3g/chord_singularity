#!/usr/bin/env bash

# Script to clone and/or update the Bento web interface
#  - Can only be called at runtime

# Load common runtime configuration
source /chord/data/.environment

cd /chord/data || exit

# If BENTO_FRONTEND_REPOSITORY or BENTO_FRONTEND_VERSION are unset, return
# without doing anything (no frontend specified; headless mode)
if [[ -z "${BENTO_FRONTEND_REPOSITORY}" ]] || [[ -z "${BENTO_FRONTEND_VERSION}" ]]; then
  # If the directory for the web front end exists, delete it
  rm -rf web

  # Make an empty web folder with a dummy index.html
  mkdir web
  cd /chord/data/web || exit
  echo "headless mode" > index.html
  mkdir public

  # Exit early
  exit 0
fi

# Clone the repository if it hasn't been done already
if [[ ! -d /chord/data/web ]]; then
  git clone --quiet --depth 1 "${BENTO_FRONTEND_REPOSITORY}" web
fi

# Update the repository if needed
cd /chord/data/web || exit
git pull --quiet

# Switch to the tree we want (tag or branch)
git checkout "${BENTO_FRONTEND_VERSION}"

# Install dependencies and build the bundle
npm install > /dev/null
npm run build > /dev/null
