#!/usr/bin/env bash
set -euo pipefail

DOCKER_BIN="${DOCKER_BIN:-docker}"
compose() {
  ${DOCKER_BIN} compose "$@"
}

PORT="${APP_PORT:-8050}"
curl -fsS "http://127.0.0.1:${PORT}/api/v1/health"
echo
compose ps
