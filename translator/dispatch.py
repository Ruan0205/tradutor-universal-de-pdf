from __future__ import annotations

from .pipeline import PipelineRunner
from .providers import make_inference_provider
from .settings import Settings, load_settings
from .store import init_store


def dispatch_job(job_id: str, settings: Settings | None = None) -> dict:
    runtime_settings = settings or load_settings()
    mode = runtime_settings.job_dispatcher.strip().lower()
    if mode == "celery":
        from .worker import process_job_task

        task = process_job_task.delay(job_id)
        return {"dispatcher": "celery", "task_id": task.id}
    if mode in {"none", "manual"}:
        return {"dispatcher": mode}

    store = init_store(runtime_settings.database_url)
    provider = make_inference_provider(runtime_settings)
    result = PipelineRunner(runtime_settings, store, provider).process_job(job_id)
    return {"dispatcher": "inline", "job": result}


def dispatch_next_if_idle(settings: Settings | None = None) -> dict:
    runtime_settings = settings or load_settings()
    store = init_store(runtime_settings.database_url)
    if store.has_running_job():
        return {"dispatcher": runtime_settings.job_dispatcher, "dispatched": False, "reason": "running"}
    next_job = store.next_queued_job()
    if not next_job:
        return {"dispatcher": runtime_settings.job_dispatcher, "dispatched": False, "reason": "empty"}

    mode = runtime_settings.job_dispatcher.strip().lower()
    if mode == "celery":
        from .worker import process_next_queued_job

        task = process_next_queued_job.delay()
        return {
            "dispatcher": "celery",
            "dispatched": True,
            "task_id": task.id,
            "job_id": next_job["id"],
            "name": next_job["original_filename"],
        }
    if mode in {"none", "manual"}:
        return {
            "dispatcher": mode,
            "dispatched": False,
            "reason": "manual",
            "job_id": next_job["id"],
            "name": next_job["original_filename"],
        }

    claimed = store.claim_next_queued_job()
    if not claimed:
        return {"dispatcher": "inline", "dispatched": False, "reason": "running"}
    provider = make_inference_provider(runtime_settings)
    result = PipelineRunner(runtime_settings, store, provider).process_job(claimed["id"])
    return {"dispatcher": "inline", "dispatched": True, "job": result}
