from __future__ import annotations

import argparse
from pathlib import Path
import time

from .settings import load_settings
from .store import init_store


def is_stable(path: Path, *, wait_seconds: float = 2.0) -> bool:
    if not path.exists() or path.suffix.lower() != ".pdf":
        return False
    first = path.stat()
    time.sleep(wait_seconds)
    second = path.stat()
    if first.st_size != second.st_size or first.st_mtime_ns != second.st_mtime_ns:
        return False
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


def scan_once() -> list[dict]:
    settings = load_settings()
    settings.ensure_dirs()
    store = init_store(settings.database_url)
    submitted = []
    for path in sorted(settings.input_dir.glob("*.pdf")):
        if not is_stable(path):
            continue
        submitted.append(store.submit_pdf(path, metadata={"submitted_by": "watcher"}))
    return submitted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args(argv)
    while True:
        scan_once()
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
