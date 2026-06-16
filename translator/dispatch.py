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
