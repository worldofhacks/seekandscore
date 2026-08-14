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
require_value OZ_IMPORTER_RUNTIME_DATABASE_URL "${OZ_IMPORTER_RUNTIME_DATABASE_URL:-}"
require_value OZ_MEMBERSHIP_RUNTIME_DATABASE_URL "${OZ_MEMBERSHIP_RUNTIME_DATABASE_URL:-}"
require_value API_DATABASE_PASSWORD "${API_DATABASE_PASSWORD:-}"
require_value INGESTION_DATABASE_PASSWORD "${INGESTION_DATABASE_PASSWORD:-}"
require_value OZ_IMPORTER_DATABASE_PASSWORD "${OZ_IMPORTER_DATABASE_PASSWORD:-}"
require_value OZ_MEMBERSHIP_DATABASE_PASSWORD "${OZ_MEMBERSHIP_DATABASE_PASSWORD:-}"

database_urls="
$MIGRATION_DATABASE_URL
$API_RUNTIME_DATABASE_URL
$INGESTION_RUNTIME_DATABASE_URL
$OZ_IMPORTER_RUNTIME_DATABASE_URL
$OZ_MEMBERSHIP_RUNTIME_DATABASE_URL
"
unique_database_urls="$(printf '%s\n' "$database_urls" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')"
if [ "$unique_database_urls" -ne 5 ]; then
  echo "database migration startup refused: owner and all runtime URLs must be distinct" >&2
  exit 1
fi

runtime_passwords="
$API_DATABASE_PASSWORD
$INGESTION_DATABASE_PASSWORD
$OZ_IMPORTER_DATABASE_PASSWORD
$OZ_MEMBERSHIP_DATABASE_PASSWORD
"
unique_runtime_passwords="$(printf '%s\n' "$runtime_passwords" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')"
if [ "$unique_runtime_passwords" -ne 4 ]; then
  echo "database migration startup refused: all runtime database passwords must be distinct" >&2
  exit 1
fi

exec "$@"
