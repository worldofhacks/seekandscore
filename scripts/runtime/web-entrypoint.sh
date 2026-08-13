#!/bin/sh
set -eu

if [ -f /app/apps/web/server.js ]; then
  exec node /app/apps/web/server.js
fi

exec node /app/server.js
