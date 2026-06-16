#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it before production use."
fi

docker compose -f compose.yaml -f compose.cpu.yaml build
docker compose -f compose.yaml -f compose.cpu.yaml up -d postgres redis
docker compose -f compose.yaml -f compose.cpu.yaml run --rm api python -m translator.cli status >/dev/null
echo "Install complete."
