#!/usr/bin/env bash
set -euo pipefail

DOCKER_BIN="${DOCKER_BIN:-docker}"
docker_cmd() {
  local docker_parts=()
  read -r -a docker_parts <<< "$DOCKER_BIN"
  "${docker_parts[@]}" "$@"
}

compose() {
  docker_cmd compose "$@"
}

PORT="${APP_PORT:-8050}"
curl -fsS "http://127.0.0.1:${PORT}/api/v1/health"
echo
compose ps
