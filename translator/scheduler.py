from __future__ import annotations

import argparse
import time

from .dispatch import dispatch_next_if_idle
from .settings import load_settings


def run_once() -> dict:
    settings = load_settings()
    settings.ensure_dirs()
    return dispatch_next_if_idle(settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=30.0)
    args = parser.parse_args(argv)
    while True:
        run_once()
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
