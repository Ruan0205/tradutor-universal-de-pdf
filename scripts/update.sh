#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DOCKER_BIN="${DOCKER_BIN:-docker}"
docker_cmd() {
  local docker_parts=()
  read -r -a docker_parts <<< "$DOCKER_BIN"
  "${docker_parts[@]}" "$@"
}

compose() {
  docker_cmd compose "$@"
}

./scripts/backup.sh
git pull --ff-only
compose -f compose.yaml -f compose.cpu.yaml build
./scripts/migrate.sh
compose -f compose.yaml -f compose.cpu.yaml up -d
./scripts/healthcheck.sh
