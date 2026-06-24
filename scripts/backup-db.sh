#!/usr/bin/env bash
set -euo pipefail

# Nightly Postgres backup for timetabler-web. Runs ON the VM via cron.
# Dumps the database from the running postgres container to a gzipped
# file and prunes backups older than RETENTION_DAYS.

APP_DIR="${APP_DIR:-$HOME/timetabler-web}"
BACKUP_DIR="$APP_DIR/backups"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml"

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

# Load DB credentials from .env.prod (VM-only, not in git).
set -a
# shellcheck disable=SC1091
. "$APP_DIR/.env.prod"
set +a

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/timetabler-$STAMP.sql.gz"

CID="$($COMPOSE ps -q postgres)"
if [ -z "$CID" ]; then
  echo "$(date -Is) ERROR: postgres container not running" >&2
  exit 1
fi

docker exec "$CID" pg_dump -U "${POSTGRES_USER:-timetabler}" -d "${POSTGRES_DB:-timetabler}" \
  | gzip > "$OUT"

# Prune old backups.
find "$BACKUP_DIR" -name 'timetabler-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "$(date -Is) backup OK: $OUT ($(du -h "$OUT" | cut -f1))"
