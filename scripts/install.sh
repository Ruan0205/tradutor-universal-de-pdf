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

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it before production use."
fi

compose -f compose.yaml -f compose.cpu.yaml build
compose -f compose.yaml -f compose.cpu.yaml up -d postgres redis
compose -f compose.yaml -f compose.cpu.yaml run --rm api python -m translator.cli status >/dev/null
echo "Install complete."
