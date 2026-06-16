# Architecture

The production layer is additive and lives under `translator/`. The legacy Windows launcher and `engine/` pipeline remain available while the new platform matures.

## Services

- `api`: FastAPI app exposing `/api/v1`.
- `worker`: Celery worker for durable background jobs.
- `watcher`: stable-file scanner for the input folder.
- `scheduler`: Celery beat placeholder for recurring maintenance.
- `postgres`: durable job/config/report storage.
- `redis`: broker/backend for Celery.
- `ollama`: local inference backend, default model target `qwen3.5:9b`.

## Data flow

PDF input -> watcher/API/CLI -> checksum and job registration -> staged pipeline -> Document IR -> translation provider -> PDF composition -> validation -> reports -> output artifacts.

## Compatibility

The new API does not remove the old dashboard or scripts. Migration should move behavior out of `engine/pipeline.py` incrementally and keep legacy entrypoints working until replacement is validated.
