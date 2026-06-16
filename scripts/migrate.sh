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

compose run --rm api python - <<'PY'
from translator.settings import load_settings
from translator.store import init_store

settings = load_settings()
settings.ensure_dirs()
init_store(settings.database_url).initialize()
print("Migrations applied.")
PY
