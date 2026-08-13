#!/bin/sh
set -eu

: "${APP_ENV:=development}"
: "${DATASET_MODE:=live}"

if [ "$DATASET_MODE" != "live" ]; then
  echo "web startup refused: DATASET_MODE must be live" >&2
  exit 1
fi

case "$APP_ENV" in
  development|test)
    ;;
  staging|production)
    if [ -z "${API_BASE_URL:-}" ]; then
      echo "web startup refused: API_BASE_URL is required in $APP_ENV" >&2
      exit 1
    fi
    if [ "${WEB_PRIVATE_ACCESS_ENABLED:-}" != "true" ]; then
      echo "web startup refused: WEB_PRIVATE_ACCESS_ENABLED must be true in $APP_ENV" >&2
      exit 1
    fi
    case "${WEB_PRIVATE_ACCESS_USERNAME:-}" in
      *[![:space:]]*) ;;
      *)
        echo "web startup refused: WEB_PRIVATE_ACCESS_USERNAME is required in $APP_ENV" >&2
        exit 1
        ;;
    esac
    case "$WEB_PRIVATE_ACCESS_USERNAME" in
      *:*)
        echo "web startup refused: WEB_PRIVATE_ACCESS_USERNAME cannot contain a colon" >&2
        exit 1
        ;;
    esac
    case "${WEB_PRIVATE_ACCESS_PASSWORD:-}" in
      *[![:space:]]*) ;;
      *)
        echo "web startup refused: WEB_PRIVATE_ACCESS_PASSWORD is required in $APP_ENV" >&2
        exit 1
        ;;
    esac
    if [ "${#WEB_PRIVATE_ACCESS_PASSWORD}" -lt 24 ]; then
      echo "web startup refused: WEB_PRIVATE_ACCESS_PASSWORD must be at least 24 characters" >&2
      exit 1
    fi
    ;;
  *)
    echo "web startup refused: unsupported APP_ENV" >&2
    exit 1
    ;;
esac

if [ -f /app/apps/web/server.js ]; then
  exec node /app/apps/web/server.js
fi

exec node /app/server.js
