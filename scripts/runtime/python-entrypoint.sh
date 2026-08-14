#!/bin/sh
set -eu

: "${DATASET_MODE:=live}"
: "${INGESTION_ENABLED:=false}"
: "${LIVE_SOURCE_DISPLAY_ENABLED:=false}"
: "${ALERT_DELIVERY_MODE:=log}"
: "${OUTREACH_MODE:=disabled}"
: "${OUTREACH_SEND_ENABLED:=false}"

export DATASET_MODE INGESTION_ENABLED LIVE_SOURCE_DISPLAY_ENABLED ALERT_DELIVERY_MODE OUTREACH_MODE OUTREACH_SEND_ENABLED

case "${APP_ENV:-development}" in
  staging|production)
    if [ -n "${MIGRATION_DATABASE_URL:-}" ]; then
      echo "runtime startup refused: MIGRATION_DATABASE_URL belongs only on db-migrate" >&2
      exit 1
    fi
    if [ "${1:-}" != "/app/scripts/runtime/database-role-entrypoint.sh" ]; then
      echo "runtime startup refused: deployed Python services require a database role audit" >&2
      exit 1
    fi
    ;;
esac

exec "$@"
