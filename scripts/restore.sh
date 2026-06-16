#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-dir>" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
SRC="$1"

if [ -f "${SRC}/data.tar.gz" ]; then
  tar -xzf "${SRC}/data.tar.gz"
fi

if [ -f "${SRC}/postgres.sql" ]; then
  docker compose up -d postgres
  docker compose exec -T postgres psql -U translator -d translator < "${SRC}/postgres.sql"
fi

echo "Restore complete from ${SRC}"
