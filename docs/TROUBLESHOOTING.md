# Troubleshooting

## API is not ready

```bash
docker compose ps
docker compose logs api
./scripts/healthcheck.sh
```

## Jobs do not run

```bash
docker compose logs worker
docker compose logs redis
```

## Model is unavailable

```bash
docker compose logs ollama
./scripts/benchmark.sh
```
