#!/bin/sh
set -eu

case "${APP_ENV:-}" in
  staging|production)
    ;;
  *)
    echo "database migration startup refused: APP_ENV must be staging or production" >&2
    exit 1
    ;;
esac

require_value() {
  name="$1"
  value="$2"
  if [ -z "$value" ]; then
    echo "database migration startup refused: $name is required" >&2
    exit 1
  fi
}

require_value MIGRATION_DATABASE_URL "${MIGRATION_DATABASE_URL:-}"
require_value API_RUNTIME_DATABASE_URL "${API_RUNTIME_DATABASE_URL:-}"
require_value INGESTION_RUNTIME_DATABASE_URL "${INGESTION_RUNTIME_DATABASE_URL:-}"
require_value API_DATABASE_PASSWORD "${API_DATABASE_PASSWORD:-}"
require_value INGESTION_DATABASE_PASSWORD "${INGESTION_DATABASE_PASSWORD:-}"

if [ "$MIGRATION_DATABASE_URL" = "$API_RUNTIME_DATABASE_URL" ] \
  || [ "$MIGRATION_DATABASE_URL" = "$INGESTION_RUNTIME_DATABASE_URL" ] \
  || [ "$API_RUNTIME_DATABASE_URL" = "$INGESTION_RUNTIME_DATABASE_URL" ]
then
  echo "database migration startup refused: owner, API, and ingestion URLs must be distinct" >&2
  exit 1
fi

exec "$@"
