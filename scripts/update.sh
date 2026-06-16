#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

./scripts/backup.sh
git pull --ff-only
docker compose -f compose.yaml -f compose.cpu.yaml build
./scripts/migrate.sh
docker compose -f compose.yaml -f compose.cpu.yaml up -d
./scripts/healthcheck.sh
