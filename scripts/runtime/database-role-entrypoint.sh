#!/bin/sh
set -eu

contract="${1:-}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "${APP_ENV:-development}" in
  development|test|preview)
    exec "$@"
    ;;
  staging|production)
    ;;
  *)
    echo "database role startup refused: unsupported APP_ENV" >&2
    exit 1
    ;;
esac

if [ -n "${MIGRATION_DATABASE_URL:-}" ]; then
  echo "database role startup refused: owner credential must not be present at runtime" >&2
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "database role startup refused: DATABASE_URL is required" >&2
  exit 1
fi

case "$contract" in
  api)
    python -m seekandscore.db.roles audit-api-runtime
    ;;
  ingestion)
    python -m seekandscore.db.roles audit-ingestion-runtime
    ;;
  unprovisioned)
    echo "database role startup refused: this service has no approved runtime role" >&2
    exit 1
    ;;
  *)
    echo "database role startup refused: unknown role contract" >&2
    exit 1
    ;;
esac

exec "$@"
