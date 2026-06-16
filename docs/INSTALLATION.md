# Installation

## Local Python

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Docker Compose

```bash
cp .env.example .env
# edit .env and provide a real admin password via Docker secret or env
docker compose -f compose.yaml -f compose.cpu.yaml build
docker compose -f compose.yaml -f compose.cpu.yaml up -d
./scripts/healthcheck.sh
```

Default LAN URL after deployment:

```text
http://10.0.0.64:8050
```
