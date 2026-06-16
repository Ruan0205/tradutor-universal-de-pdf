# Security

## Secrets

Never commit passwords, API keys, model credentials, SSH credentials, private server paths, PDFs, model files, or cache directories.

Use:

- `.env` outside Git
- Docker secrets
- volume-mounted configuration
- per-server override files excluded from Git

## External services

Google and other external providers are disabled by default. Do not send document content to external APIs unless the operator explicitly enables the integration and accepts cost/privacy implications.

## Network exposure

The default deployment target is LAN-only with authentication. Do not expose the dashboard publicly without TLS, authentication, firewall review, and secret rotation.

## Reporting

Report security issues privately to the repository maintainer. Do not open public issues containing credentials, paths, PDFs, or logs with sensitive data.
