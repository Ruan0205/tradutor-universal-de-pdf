#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <git-ref> [backup-dir]" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
REF="$1"
BACKUP="${2:-}"

DOCKER_BIN="${DOCKER_BIN:-docker}"
docker_cmd() {
  local docker_parts=()
  read -r -a docker_parts <<< "$DOCKER_BIN"
  "${docker_parts[@]}" "$@"
}

compose() {
  docker_cmd compose "$@"
}

git checkout "$REF"
compose -f compose.yaml -f compose.cpu.yaml build
if [ -n "$BACKUP" ]; then
  ./scripts/restore.sh "$BACKUP"
fi
compose -f compose.yaml -f compose.cpu.yaml up -d
./scripts/healthcheck.sh
