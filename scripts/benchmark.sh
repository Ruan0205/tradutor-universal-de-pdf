#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL="${LLM_MODEL:-qwen3.5:9b}"
BASE_URL="${LLM_BASE_URL:-http://localhost:11434}"

python - <<PY
from translator.providers.inference import OllamaProvider, TranslationRequest
import time

provider = OllamaProvider("${BASE_URL}", "${MODEL}", timeout=120, retries=1)
print(provider.health())
sample = "The wizard casts a spell at the beginning of the round."
start = time.perf_counter()
result = provider.translate(TranslationRequest(block_id="bench-1", text=sample))
elapsed = time.perf_counter() - start
print({"elapsed_seconds": round(elapsed, 3), "result": result.translated_text[:200]})
PY
