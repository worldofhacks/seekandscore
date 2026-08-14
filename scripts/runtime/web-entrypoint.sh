#!/bin/sh
set -eu

: "${APP_ENV:=development}"
: "${DATASET_MODE:=live}"

if [ "$DATASET_MODE" != "live" ]; then
  echo "web startup refused: DATASET_MODE must be live" >&2
  exit 1
fi

if [ "${NODE_ENV:-}" = "production" ] && { [ "$APP_ENV" = "development" ] || [ "$APP_ENV" = "test" ]; }; then
  echo "web startup refused: a production process cannot use APP_ENV=$APP_ENV" >&2
  exit 1
fi

case "$APP_ENV" in
  development|test)
    if [ "${RESEARCH_WRITES_ENABLED:-false}" = "true" ]; then
      echo "web startup refused: saved research is disabled in development and test runtimes" >&2
      exit 1
    fi
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
    if [ "${RESEARCH_WRITES_ENABLED:-false}" = "true" ]; then
      case "${API_BASE_URL%/}" in
        http://api.railway.internal:8000) ;;
        *)
          echo "web startup refused: research writes require the exact private Railway API origin" >&2
          exit 1
          ;;
      esac
      research_internal_token_value=${RESEARCH_INTERNAL_TOKEN:-}
      if [ "${#research_internal_token_value}" -lt 32 ]; then
        echo "web startup refused: RESEARCH_INTERNAL_TOKEN must be at least 32 characters when research writes are enabled" >&2
        exit 1
      fi
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
