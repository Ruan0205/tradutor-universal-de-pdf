#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DOCKER_BIN="${DOCKER_BIN:-docker}"
TAR_BIN="${TAR_BIN:-tar}"
docker_cmd() {
  local docker_parts=()
  read -r -a docker_parts <<< "$DOCKER_BIN"
  "${docker_parts[@]}" "$@"
}

tar_cmd() {
  local tar_parts=()
  read -r -a tar_parts <<< "$TAR_BIN"
  "${tar_parts[@]}" "$@"
}

compose() {
  docker_cmd compose "$@"
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${BACKUP_DIR:-./backups}"
DEST="${BACKUP_ROOT}/${STAMP}"
DATA_ROOT="${DATA_DIR_FOR_BACKUP:-${BASE_DIR:-./data}}"
mkdir -p "$DEST"

if compose ps postgres >/dev/null 2>&1; then
  compose exec -T postgres pg_dump -U translator -d translator > "${DEST}/postgres.sql"
fi

if [ -d "$DATA_ROOT" ]; then
  tar_cmd -czf "${DEST}/data.tar.gz" -C "$DATA_ROOT" --exclude=./backups --exclude=backups .
fi

cp .env "${DEST}/env.backup" 2>/dev/null || true
echo "Backup written to ${DEST}"
