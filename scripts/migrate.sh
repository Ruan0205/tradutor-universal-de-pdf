#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose run --rm api python - <<'PY'
from translator.settings import load_settings
from translator.store import init_store

settings = load_settings()
settings.ensure_dirs()
init_store(settings.database_url).initialize()
print("Migrations applied.")
PY
