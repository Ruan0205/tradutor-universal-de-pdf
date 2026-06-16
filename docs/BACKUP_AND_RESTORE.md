# Backup and Restore

Backup:

```bash
./scripts/backup.sh
```

Restore:

```bash
./scripts/restore.sh <backup-dir>
```

Backups include database dump when Postgres is running and local `data/` when present. Original PDFs are not sent to external locations by these scripts.
