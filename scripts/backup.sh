#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DOCKER_BIN="${DOCKER_BIN:-docker}"
compose() {
  ${DOCKER_BIN} compose "$@"
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${BACKUP_DIR:-./backups}"
DEST="${BACKUP_ROOT}/${STAMP}"
mkdir -p "$DEST"

if compose ps postgres >/dev/null 2>&1; then
  compose exec -T postgres pg_dump -U translator -d translator > "${DEST}/postgres.sql"
fi

if [ -d data ]; then
  tar -czf "${DEST}/data.tar.gz" data
fi

cp .env "${DEST}/env.backup" 2>/dev/null || true
echo "Backup written to ${DEST}"
