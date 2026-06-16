from __future__ import annotations

from pathlib import Path
import secrets
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from .domain import JobStatus
from .pipeline import PipelineRunner
from .providers import make_inference_provider
from .providers.ocr import OCRmyPDFProvider, RapidOCRProvider, TesseractProvider
from .settings import Settings, load_settings
from .store import JobStore, init_store


class SubmitRequest(BaseModel):
    path: str
    priority: int = 0
    authorized: bool = False


class JobActionResponse(BaseModel):
    ok: bool
    job_id: str
    status: str


security = HTTPBasic(auto_error=False)


def get_settings() -> Settings:
    settings = load_settings()
    settings.ensure_dirs()
    return settings


def get_store(settings: Settings = Depends(get_settings)) -> JobStore:
    return init_store(settings.database_url)


def require_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.auth_enabled:
        return
    expected_password = settings.admin_password()
    if not expected_password:
        raise HTTPException(status_code=503, detail="Authentication is enabled but no admin password is configured")
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Basic"})
    ok_user = secrets.compare_digest(credentials.username, settings.initial_admin_user)
    ok_pass = secrets.compare_digest(credentials.password, expected_password)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})


def create_app() -> FastAPI:
    app = FastAPI(title="Tradutor Universal de PDF", version="3.0.0-rc.1")

    @app.get("/", response_class=HTMLResponse)
    def index(_: None = Depends(require_auth)):
        return HTMLResponse(_dashboard_html())

    @app.get("/api/v1/health")
    def health(settings: Settings = Depends(get_settings)):
        return {"ok": True, "service": "api", "environment": settings.app_env}

    @app.get("/api/v1/ready")
    def ready(store: JobStore = Depends(get_store)):
        store.initialize()
        return {"ok": True, "database": "ready"}

    @app.get("/api/v1/metrics")
    def metrics(_: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        jobs = store.list_jobs(limit=1000)
        counts = {}
        for job in jobs:
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        return {"jobs": counts}

    @app.get("/api/v1/jobs")
    def list_jobs(_: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        return {"jobs": store.list_jobs()}

    @app.post("/api/v1/jobs")
    def submit_job(
        request: SubmitRequest,
        background: BackgroundTasks,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        path = Path(request.path)
        if not path.exists() or path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Path must point to an existing PDF")
        job = store.submit_pdf(path, priority=request.priority, metadata={"authorized": request.authorized})
        background.add_task(_process_job_background, job["id"], settings)
        return job

    @app.post("/api/v1/jobs/upload")
    async def upload_job(
        file: UploadFile,
        background: BackgroundTasks,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF uploads are accepted")
        target = settings.input_dir / Path(file.filename).name
        with target.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                fh.write(chunk)
        job = store.submit_pdf(target, metadata={"authorized": False, "submitted_by": "upload"})
        background.add_task(_process_job_background, job["id"], settings)
        return job

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        job = store.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/api/v1/jobs/{job_id}/pages")
    def get_pages(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        artifacts = store.list_artifacts(job_id)
        ir_artifact = next((item for item in artifacts if item["kind"] == "document_ir"), None)
        if not ir_artifact:
            return {"pages": []}
        import json

        data = json.loads(Path(ir_artifact["path"]).read_text(encoding="utf-8"))
        return {"pages": data.get("pages", [])}

    @app.get("/api/v1/jobs/{job_id}/artifacts")
    def get_artifacts(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        return {"artifacts": store.list_artifacts(job_id)}

    @app.get("/api/v1/jobs/{job_id}/stages")
    def get_stages(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        return {"stages": store.list_stages(job_id)}

    @app.post("/api/v1/jobs/{job_id}/pause", response_model=JobActionResponse)
    def pause_job(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        job = store.update_job(job_id, status=JobStatus.PAUSED.value)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.post("/api/v1/jobs/{job_id}/resume", response_model=JobActionResponse)
    def resume_job(
        job_id: str,
        background: BackgroundTasks,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        job = store.update_job(job_id, status=JobStatus.QUEUED.value)
        background.add_task(_process_job_background, job_id, settings)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=JobActionResponse)
    def retry_job(
        job_id: str,
        background: BackgroundTasks,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        job = store.update_job(job_id, status=JobStatus.QUEUED.value, error=None)
        background.add_task(_process_job_background, job_id, settings)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobActionResponse)
    def cancel_job(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        job = store.update_job(job_id, status=JobStatus.CANCELLED.value)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.get("/api/v1/glossaries")
    def glossaries(_: None = Depends(require_auth)):
        return {"glossaries": []}

    @app.get("/api/v1/models")
    def models(_: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        provider = make_inference_provider(settings)
        return provider.health()

    @app.get("/api/v1/providers")
    def providers(_: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        inference = make_inference_provider(settings)
        return {
            "inference": inference.health(),
            "ocr": [RapidOCRProvider().health(), TesseractProvider().health(), OCRmyPDFProvider().health()],
            "google_enabled": settings.google_integration_enabled,
        }

    return app


def _process_job_background(job_id: str, settings: Settings) -> None:
    store = init_store(settings.database_url)
    provider = make_inference_provider(settings)
    PipelineRunner(settings, store, provider).process_job(job_id)


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tradutor Universal de PDF</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; background: #111827; color: #f9fafb; }
    table { border-collapse: collapse; width: 100%; background: #1f2937; }
    th, td { border-bottom: 1px solid #374151; padding: 8px; text-align: left; }
    button { padding: 8px 12px; }
    code { color: #93c5fd; }
  </style>
</head>
<body>
  <h1>Tradutor Universal de PDF</h1>
  <p>API v1 ativa. Use <code>/api/v1/jobs</code>, <code>/api/v1/health</code> e <code>/api/v1/metrics</code>.</p>
  <button onclick="loadJobs()">Atualizar fila</button>
  <table><thead><tr><th>Job</th><th>Arquivo</th><th>Status</th><th>Etapa</th><th>Progresso</th></tr></thead><tbody id="jobs"></tbody></table>
  <script>
    async function loadJobs() {
      const r = await fetch('/api/v1/jobs');
      const data = await r.json();
      document.getElementById('jobs').innerHTML = (data.jobs || []).map(j =>
        `<tr><td>${j.id}</td><td>${j.original_filename}</td><td>${j.status}</td><td>${j.current_stage || ''}</td><td>${j.progress}%</td></tr>`
      ).join('');
    }
    loadJobs();
  </script>
</body>
</html>"""


app = create_app()
