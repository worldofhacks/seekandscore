#!/bin/sh
set -eu

: "${APP_ENV:=development}"
: "${DATASET_MODE:=live}"

if [ "$DATASET_MODE" != "live" ]; then
  echo "web startup refused: DATASET_MODE must be live" >&2
  exit 1
fi

case "$APP_ENV" in
  staging|production)
    if [ -z "${API_BASE_URL:-}" ]; then
      echo "web startup refused: API_BASE_URL is required in $APP_ENV" >&2
      exit 1
    fi
    ;;
esac

if [ -f /app/apps/web/server.js ]; then
  exec node /app/apps/web/server.js
fi

exec node /app/server.js
