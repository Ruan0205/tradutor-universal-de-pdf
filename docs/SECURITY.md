# Security Notes

- LAN-only by default.
- Authentication should be enabled in production.
- External document APIs are disabled by default.
- Secrets must live in `.env`, Docker secrets, or external configuration, never in Git.
- Do not publish server-specific paths or credentials.
