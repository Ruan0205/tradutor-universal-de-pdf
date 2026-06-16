from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import PipelineRunner
from .providers import make_inference_provider
from .settings import load_settings
from .store import init_store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="translator")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("pdf")
    submit.add_argument("--priority", type=int, default=0)
    submit.add_argument("--run", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("job_id", nargs="?")
    for name in ["pause", "resume", "retry", "validate", "export"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("job_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    settings.ensure_dirs()
    store = init_store(settings.database_url)

    if args.command == "submit":
        job = store.submit_pdf(Path(args.pdf), priority=args.priority, metadata={"submitted_by": "cli"})
        if args.run:
            provider = make_inference_provider(settings)
            job = PipelineRunner(settings, store, provider).process_job(job["id"])
        print(json.dumps(job, indent=2, ensure_ascii=False))
        return 0

    if args.command == "status":
        data = store.get_job(args.job_id) if args.job_id else {"jobs": store.list_jobs()}
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    if args.command == "pause":
        print(json.dumps(store.update_job(args.job_id, status="paused"), indent=2, ensure_ascii=False))
        return 0

    if args.command in {"resume", "retry"}:
        job = store.update_job(args.job_id, status="queued", error=None)
        provider = make_inference_provider(settings)
        PipelineRunner(settings, store, provider).process_job(args.job_id)
        print(json.dumps(job, indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate":
        print(json.dumps({"job_id": args.job_id, "stages": store.list_stages(args.job_id)}, indent=2, ensure_ascii=False))
        return 0

    if args.command == "export":
        print(json.dumps({"job_id": args.job_id, "artifacts": store.list_artifacts(args.job_id)}, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
