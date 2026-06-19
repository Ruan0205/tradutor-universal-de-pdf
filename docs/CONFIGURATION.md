# Configuration

Configuration comes from environment variables. Use `.env.example` as the public template and keep `.env` private.

Important defaults:

- `APP_PORT=8050`
- `AUTH_ENABLED=true`
- `LLM_PROVIDER=ollama`
- `LLM_MODEL=qwen3.5:9b`
- `GOOGLE_INTEGRATION_ENABLED=false`
- `MAX_CONCURRENT_BOOKS=1`

Do not commit private server paths, passwords, API keys, or provider credentials.
