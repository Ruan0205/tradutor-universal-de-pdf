from __future__ import annotations

from celery import Celery

from .pipeline import PipelineRunner
from .providers import make_inference_provider
from .settings import load_settings
from .store import init_store


settings = load_settings()
celery_app = Celery("translator", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.beat_schedule = {
    "process-next-queued-job": {
        "task": "translator.process_next_queued_job",
        "schedule": 30.0,
    }
}


@celery_app.task(name="translator.process_job")
def process_job_task(job_id: str) -> dict:
    runtime_settings = load_settings()
    runtime_settings.ensure_dirs()
    store = init_store(runtime_settings.database_url)
    current = store.get_job(job_id)
    if current and current["status"] != "running" and store.has_running_job():
        return {"processed": False, "job_id": job_id, "reason": "busy"}
    claimed = store.claim_job(job_id)
    if not claimed or claimed["status"] != "running":
        return store.get_job(job_id) or {"id": job_id, "status": "missing"}
    provider = make_inference_provider(runtime_settings)
    return PipelineRunner(runtime_settings, store, provider).process_job(job_id)


@celery_app.task(name="translator.process_next_queued_job")
def process_next_queued_job() -> dict:
    runtime_settings = load_settings()
    runtime_settings.ensure_dirs()
    store = init_store(runtime_settings.database_url)
    if store.has_running_job():
        return {"processed": False, "reason": "busy"}
    job = store.claim_next_queued_job()
    if not job:
        return {"processed": False, "reason": "empty"}
    provider = make_inference_provider(runtime_settings)
    result = PipelineRunner(runtime_settings, store, provider).process_job(job["id"])
    return {"processed": True, "job_id": result["id"], "status": result["status"]}
