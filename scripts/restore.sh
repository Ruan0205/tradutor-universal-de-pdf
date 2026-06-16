#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-dir>" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
SRC="$1"

DOCKER_BIN="${DOCKER_BIN:-docker}"
compose() {
  ${DOCKER_BIN} compose "$@"
}

if [ -f "${SRC}/data.tar.gz" ]; then
  tar -xzf "${SRC}/data.tar.gz"
fi

if [ -f "${SRC}/postgres.sql" ]; then
  compose up -d postgres
  if [ "${RESTORE_RESET_DB:-true}" = "true" ]; then
    compose exec -T postgres psql -U translator -d translator -v ON_ERROR_STOP=1 \
      -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
  fi
  compose exec -T postgres psql -U translator -d translator -v ON_ERROR_STOP=1 < "${SRC}/postgres.sql"
fi

echo "Restore complete from ${SRC}"
