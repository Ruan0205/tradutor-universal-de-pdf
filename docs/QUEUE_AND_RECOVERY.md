# Queue and Recovery

Jobs are registered durably with checksum deduplication. Celery and Redis provide background execution in Docker. Job stages are persisted so interrupted work can be inspected and retried.

Operational commands:

```bash
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
docker compose up -d
```
