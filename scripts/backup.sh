#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${BACKUP_DIR:-./backups}"
DEST="${BACKUP_ROOT}/${STAMP}"
mkdir -p "$DEST"

if docker compose ps postgres >/dev/null 2>&1; then
  docker compose exec -T postgres pg_dump -U translator translator > "${DEST}/postgres.sql" || true
fi

if [ -d data ]; then
  tar -czf "${DEST}/data.tar.gz" data
fi

cp .env "${DEST}/env.backup" 2>/dev/null || true
echo "Backup written to ${DEST}"
