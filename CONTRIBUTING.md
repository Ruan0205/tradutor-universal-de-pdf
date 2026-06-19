# Contributing

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q .
```

Keep PDFs, models, caches, `.env`, secrets, and local server paths out of Git.

## Branches and commits

- Work on feature branches, not `main`.
- Use small commits with clear messages.
- Do not force push shared branches.
- Run tests before opening a PR.
