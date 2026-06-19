from __future__ import annotations

import json
from pathlib import Path
import secrets
import time
from typing import Annotated
import urllib.request

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from .dispatch import dispatch_job
from .domain import JobStatus
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


class GlossaryTermRequest(BaseModel):
    source_term: str
    target_term: str
    notes: str = ""


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
        return HTMLResponse(_legacy_dashboard_html())

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
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        path = Path(request.path)
        if not path.exists() or path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Path must point to an existing PDF")
        job = store.submit_pdf(path, priority=request.priority, metadata={"authorized": request.authorized})
        if job["status"] == JobStatus.QUEUED.value:
            dispatch_job(job["id"], settings)
        return job

    @app.post("/api/v1/jobs/upload")
    async def upload_job(
        file: UploadFile,
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
        if job["status"] == JobStatus.QUEUED.value:
            dispatch_job(job["id"], settings)
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

    @app.get("/api/v1/jobs/{job_id}/artifacts/{artifact_id}/download")
    def download_artifact(
        job_id: str,
        artifact_id: int,
        _: None = Depends(require_auth),
        store: JobStore = Depends(get_store),
    ):
        artifact = store.get_artifact(artifact_id)
        if not artifact or artifact["job_id"] != job_id:
            raise HTTPException(status_code=404, detail="Artifact not found")
        path = Path(artifact["path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file is missing")
        return FileResponse(path, filename=path.name)

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
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        job = store.update_job(job_id, status=JobStatus.QUEUED.value)
        dispatch_job(job_id, settings)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=JobActionResponse)
    def retry_job(
        job_id: str,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        job = store.update_job(job_id, status=JobStatus.QUEUED.value, error=None)
        dispatch_job(job_id, settings)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobActionResponse)
    def cancel_job(job_id: str, _: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        job = store.update_job(job_id, status=JobStatus.CANCELLED.value)
        return {"ok": True, "job_id": job_id, "status": job["status"]}

    @app.get("/api/v1/glossaries")
    def glossaries(_: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        return {"terms": store.list_glossary_terms()}

    @app.post("/api/v1/glossaries")
    def upsert_glossary_term(
        request: GlossaryTermRequest,
        _: None = Depends(require_auth),
        store: JobStore = Depends(get_store),
    ):
        term = store.upsert_glossary_term(request.source_term, request.target_term, notes=request.notes)
        return {"ok": True, "term": term}

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

    @app.get("/api/status")
    def legacy_status(_: None = Depends(require_auth), settings: Settings = Depends(get_settings), store: JobStore = Depends(get_store)):
        return _legacy_status(settings, store)

    @app.get("/api/config")
    def legacy_get_config(_: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        return _legacy_load_config(settings)

    @app.post("/api/config")
    async def legacy_save_config(
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
    ):
        update_data = await request.json()
        config = _legacy_load_config(settings)
        config.update(update_data)
        _legacy_save_config(settings, config)
        return {"ok": True, "config": config}

    @app.post("/api/model")
    async def legacy_set_model(
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
    ):
        data = await request.json()
        model = str(data.get("model") or "").strip()
        if not model:
            raise HTTPException(status_code=400, detail="Model is required")
        config = _legacy_load_config(settings)
        config["model_name"] = model
        config["validation_model"] = model
        _legacy_save_config(settings, config)
        return {"ok": True, "model": model}

    @app.post("/api/start")
    def legacy_start(_: None = Depends(require_auth), settings: Settings = Depends(get_settings), store: JobStore = Depends(get_store)):
        submitted = []
        for path in sorted(settings.input_dir.glob("*.pdf")):
            job = store.submit_pdf(path, metadata={"submitted_by": "dashboard", "authorized": False}, reuse_existing=False)
            if job["status"] == JobStatus.QUEUED.value:
                dispatch_job(job["id"], settings)
            submitted.append({"id": job["id"], "name": path.name, "status": job["status"]})
        return {"ok": True, "submitted": submitted}

    @app.post("/api/stop")
    def legacy_stop(_: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        changed = []
        for job in store.list_jobs(limit=1000):
            if job["status"] in {JobStatus.QUEUED.value, JobStatus.RUNNING.value, JobStatus.PAUSED.value}:
                changed.append(store.update_job(job["id"], status=JobStatus.CANCELLED.value))
        return {"ok": True, "jobs": changed}

    @app.post("/api/pause")
    def legacy_pause(_: None = Depends(require_auth), store: JobStore = Depends(get_store)):
        changed = []
        for job in store.list_jobs(limit=1000):
            if job["status"] in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
                changed.append(store.update_job(job["id"], status=JobStatus.PAUSED.value))
        return {"ok": True, "jobs": changed}

    @app.post("/api/resume")
    def legacy_resume(
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        changed = []
        for job in store.list_jobs(limit=1000):
            if job["status"] == JobStatus.PAUSED.value:
                resumed = store.update_job(job["id"], status=JobStatus.QUEUED.value, error=None)
                dispatch_job(job["id"], settings)
                changed.append(resumed)
        return {"ok": True, "jobs": changed}

    @app.post("/api/upload-pdfs")
    async def legacy_upload_pdfs(
        files: list[UploadFile] = File(...),
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
    ):
        added: list[str] = []
        overwritten: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for upload in files:
            if not upload.filename or not upload.filename.lower().endswith(".pdf"):
                skipped.append(upload.filename or "unknown")
                continue
            target = settings.input_dir / Path(upload.filename).name
            existed = target.exists()
            try:
                with target.open("wb") as fh:
                    while chunk := await upload.read(1024 * 1024):
                        fh.write(chunk)
                (overwritten if existed else added).append(target.name)
            except Exception as exc:
                errors.append(f"{upload.filename}: {exc}")
        return {"ok": not errors, "added": added, "overwritten": overwritten, "skipped": skipped, "errors": errors}

    @app.post("/api/retranslate")
    async def legacy_retranslate(
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        data = await request.json()
        filename = Path(str(data.get("filename") or "")).name
        original = settings.originals_dir / filename
        if not original.exists():
            return {"ok": False, "error": "Original not found for retranslation"}
        target = settings.input_dir / original.name
        target.write_bytes(original.read_bytes())
        job = store.submit_pdf(target, priority=100, metadata={"submitted_by": "dashboard", "retranslate": True})
        dispatch_job(job["id"], settings)
        return {"ok": True, "message": f"{filename} queued for retranslation", "job": job}

    @app.post("/api/revalidate")
    async def legacy_revalidate(request: Request, _: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        data = await request.json()
        filename = Path(str(data.get("filename") or "")).name
        report = _legacy_validation_for(settings, filename)
        return {"ok": True, "result": report}

    @app.post("/api/open-directory")
    async def legacy_open_directory(request: Request, _: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        data = await request.json()
        name = str(data.get("directory") or "")
        paths = {
            "input": settings.input_dir,
            "translated": settings.output_dir,
            "output": settings.output_dir,
            "originals": settings.originals_dir,
        }
        return {"ok": name in paths, "path": str(paths.get(name, settings.base_dir))}

    @app.post("/api/order")
    async def legacy_order(request: Request, _: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        data = await request.json()
        config = _legacy_load_config(settings)
        config["sort_order"] = data.get("sort_order", config.get("sort_order", "smallest_first"))
        config["custom_order"] = data.get("custom_order", config.get("custom_order", []))
        _legacy_save_config(settings, config)
        return {"ok": True, "config": config}

    @app.post("/api/queue/next")
    async def legacy_queue_next(
        request: Request,
        _: None = Depends(require_auth),
        store: JobStore = Depends(get_store),
    ):
        data = await request.json()
        filename = Path(str(data.get("filename") or "")).name
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")
        queued = [job for job in store.list_jobs(limit=1000) if job["status"] == JobStatus.QUEUED.value]
        target = next((job for job in queued if job["original_filename"] == filename or job["id"] == filename), None)
        if not target:
            raise HTTPException(status_code=404, detail="Queued book not found")
        max_priority = max([int(job.get("priority") or 0) for job in queued] or [0])
        updated = store.update_job(target["id"], priority=max_priority + 100)
        return {"ok": True, "job": updated}

    @app.post("/api/queue/order")
    async def legacy_queue_order(
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
        store: JobStore = Depends(get_store),
    ):
        data = await request.json()
        order = [Path(str(item)).name for item in data.get("order", []) if str(item).strip()]
        if not order:
            raise HTTPException(status_code=400, detail="order is required")
        queued = [job for job in store.list_jobs(limit=1000) if job["status"] == JobStatus.QUEUED.value]
        by_name = {job["original_filename"]: job for job in queued}
        base = len(order) * 10
        updated = []
        for index, name in enumerate(order):
            job = by_name.get(name)
            if not job:
                continue
            updated.append(store.update_job(job["id"], priority=base - index))
        config = _legacy_load_config(settings)
        config["sort_order"] = "custom"
        config["custom_order"] = order
        _legacy_save_config(settings, config)
        return {"ok": True, "updated": updated, "config": config}

    @app.post("/api/set-original")
    async def legacy_set_original(request: Request, _: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        data = await request.json()
        config = _legacy_load_config(settings)
        mappings = dict(config.get("original_mappings") or {})
        translated = str(data.get("translated") or "")
        original = str(data.get("original") or "")
        if translated:
            if original:
                mappings[translated] = original
            else:
                mappings.pop(translated, None)
        config["original_mappings"] = mappings
        _legacy_save_config(settings, config)
        return {"ok": True, "mapping": mappings}

    @app.get("/pdf/translated/{filename:path}")
    def legacy_pdf_translated(
        filename: str,
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
    ):
        return _safe_pdf_response(settings.output_dir, filename, download=request.query_params.get("download") == "1")

    @app.get("/pdf/original/{filename:path}")
    def legacy_pdf_original(
        filename: str,
        request: Request,
        _: None = Depends(require_auth),
        settings: Settings = Depends(get_settings),
    ):
        return _safe_pdf_response(settings.originals_dir, filename, download=request.query_params.get("download") == "1")

    @app.get("/pdf/in-progress")
    def legacy_pdf_in_progress(_: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        candidates = sorted(settings.output_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise HTTPException(status_code=404, detail="No in-progress PDF is available")
        return FileResponse(candidates[0], filename=candidates[0].name, media_type="application/pdf", content_disposition_type="inline")

    @app.get("/pdf/in-progress/{filename:path}")
    def legacy_pdf_in_progress_named(filename: str, _: None = Depends(require_auth), settings: Settings = Depends(get_settings)):
        return _safe_pdf_response(settings.output_dir, filename)

    return app


def _legacy_dashboard_html() -> str:
    path = Path(__file__).resolve().parent.parent / "engine" / "static" / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return "<!doctype html><html><body><h1>Tradutor Universal de PDF</h1></body></html>"


def _legacy_config_path(settings: Settings) -> Path:
    return settings.base_dir / "dashboard_config.json"


def _legacy_config_defaults(settings: Settings) -> dict:
    return {
        "ollama_url": settings.llm_base_url,
        "model_name": settings.llm_model,
        "validation_model": settings.llm_model,
        "validation_pages": 10,
        "validation_method": "structural",
        "image_text_mode": settings.image_text_mode,
        "google_translate_images_enabled": False,
        "compute_backend": "cpu",
        "image_ai_selectable_only": True,
        "image_inpaint_radius": 3,
        "font_pack_dir": "assets/fonts",
        "live_preview_enabled": True,
        "resource_profile": "cpu_ram",
        "source_lang": "English",
        "target_lang": "Brazilian Portuguese",
        "sort_order": "smallest_first",
        "custom_order": [],
        "max_batch_chars": 2200,
        "ollama_timeout_sec": settings.llm_timeout_seconds,
        "ollama_options": {
            "temperature": settings.llm_temperature,
            "top_p": 0.9,
            "num_ctx": settings.llm_context_tokens or 32768,
            "num_gpu": settings.llm_num_gpu if settings.llm_num_gpu is not None else 0,
        },
        "original_mappings": {},
        "validation_mode": "25%",
        "fidelity_threshold": 90,
        "retranslate_queue": [],
    }


def _legacy_load_config(settings: Settings) -> dict:
    defaults = _legacy_config_defaults(settings)
    path = _legacy_config_path(settings)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            defaults.update(stored)
        except Exception:
            pass
    return defaults


def _legacy_save_config(settings: Settings, config: dict) -> None:
    path = _legacy_config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _legacy_status(settings: Settings, store: JobStore) -> dict:
    jobs = store.list_jobs(limit=1000)
    running = next((job for job in jobs if job["status"] == JobStatus.RUNNING.value), None)
    paused = next((job for job in jobs if job["status"] == JobStatus.PAUSED.value), None)
    queued = [job for job in jobs if job["status"] == JobStatus.QUEUED.value]
    completed = [job for job in jobs if job["status"] in {JobStatus.COMPLETED.value, JobStatus.NEEDS_REVIEW.value}]
    status = "running" if running else "paused" if paused else "idle"
    books = _legacy_books(settings, jobs)
    total = len(completed) + len(queued) + (1 if running else 0) + len(books["input"])
    state_job = running or paused
    current_metadata = state_job.get("metadata", {}) if state_job else {}
    current_metrics = current_metadata.get("translation_metrics", {}) if state_job else {}
    current_elapsed = _job_elapsed_seconds(state_job) if state_job else None
    completed_durations = [_job_elapsed_seconds(job) for job in completed]
    completed_durations = [value for value in completed_durations if value and value > 0]
    avg_book_seconds = (sum(completed_durations) / len(completed_durations)) if completed_durations else None
    remaining_books = len(queued) + len(books["input"]) + (1 if running else 0)
    eta_seconds = None
    if running and state_job.get("progress", 0) > 0 and current_elapsed:
        eta_seconds = max(0.0, (current_elapsed / max(1.0, float(state_job["progress"]))) * (100.0 - float(state_job["progress"])))
        eta_seconds += max(0, remaining_books - 1) * (avg_book_seconds or 0)
    elif avg_book_seconds:
        eta_seconds = remaining_books * avg_book_seconds
    aggregate_metrics = _aggregate_translation_metrics(jobs)
    active_tokens_per_second = current_metrics.get("tokens_per_second") or aggregate_metrics.get("tokens_per_second")
    total_elapsed = sum(completed_durations) + (current_elapsed or 0.0)
    state = {
        "status": status,
        "current_book": (
            {"filename": state_job["original_filename"], "size_mb": _file_size_mb(Path(state_job["source_path"]))}
            if state_job
            else None
        ),
        "current_page": state_job["current_page"] if state_job else 0,
        "total_pages": state_job["total_pages"] if state_job else 0,
        "current_stage": state_job["current_stage"] if state_job else None,
        "book_index": len(completed) + (1 if state_job else 0),
        "total_books": max(total, len(books["input"]) + len(books["translated"])),
    }
    stats = {
        "completed": len(completed),
        "total": max(total, len(books["input"]) + len(books["translated"])),
        "eta_str": _format_duration(eta_seconds) if eta_seconds is not None else "--",
        "finish_time": _finish_time(eta_seconds) if eta_seconds is not None else "--",
        "sec_per_mb": _seconds_per_mb(completed),
        "current_elapsed_sec": current_elapsed,
        "total_elapsed_sec": total_elapsed if total_elapsed > 0 else None,
        "tokens_per_second": round(float(active_tokens_per_second or 0.0), 2) or None,
        "current_tokens_per_second": round(float(current_metrics.get("tokens_per_second") or 0.0), 2) or None,
        "total_tokens": int(aggregate_metrics.get("total_tokens") or 0),
        "completion_tokens": int(aggregate_metrics.get("completion_tokens") or 0),
        "prompt_tokens": int(aggregate_metrics.get("prompt_tokens") or 0),
        "current_total_tokens": int(current_metrics.get("total_tokens") or 0),
    }
    return {
        "status": status,
        "state": state,
        "stats": stats,
        "config": _legacy_load_config(settings),
        "books": books,
        "ollama": _legacy_ollama_status(settings),
        "preview": {"available": False},
        "validator_alive": True,
        "pipeline_alive": True,
    }


def _legacy_books(settings: Settings, jobs: list[dict] | None = None) -> dict:
    validations = _legacy_validations(settings)
    jobs = jobs or []
    jobs_by_source = {Path(job["source_path"]).stem: job for job in jobs}
    input_books = _legacy_untranslated_books(settings, jobs)
    translated_books = _list_pdfs(settings.output_dir, sort_mode="mtime_desc", suffix=".traduzido.pdf")
    return {
        "input": input_books,
        "untranslated": input_books,
        "translating": [],
        "translated": [
            {
                **item,
                "validation": validations.get(item["name"]),
                "timing": _book_timing(jobs_by_source.get(_source_stem_from_output(item["name"]))),
                "tokens": _book_tokens(jobs_by_source.get(_source_stem_from_output(item["name"]))),
            }
            for item in translated_books
        ],
        "originals": _list_pdfs(settings.originals_dir),
        "validations": validations,
        "mapping": {},
        "counts": {
            "input": len(input_books),
            "untranslated": len(input_books),
            "translating": 0,
            "translated": len(translated_books),
            "originals": len(_list_pdfs(settings.originals_dir)),
        },
    }


def _legacy_untranslated_books(settings: Settings, jobs: list[dict]) -> list[dict]:
    translated_stems = {
        _source_stem_from_output(path.name)
        for path in settings.output_dir.glob("*.traduzido.pdf")
        if path.is_file()
    }
    queued = [job for job in jobs if job["status"] == JobStatus.QUEUED.value]
    queued.sort(key=lambda job: (-int(job.get("priority") or 0), str(job.get("created_at") or "")))

    seen: set[str] = set()
    items: list[dict] = []
    for job in queued:
        source = Path(job["source_path"])
        stem = source.stem
        if stem in translated_stems or job["original_filename"] in seen:
            continue
        seen.add(job["original_filename"])
        items.append(
            {
                "name": job["original_filename"],
                "size_mb": _file_size_mb(source),
                "mtime": source.stat().st_mtime if source.exists() else 0,
                "modified": (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(source.stat().st_mtime))
                    if source.exists()
                    else ""
                ),
                "job_id": job["id"],
                "status": job["status"],
                "priority": int(job.get("priority") or 0),
                "queued": True,
            }
        )

    config = _legacy_load_config(settings)
    input_items = _list_pdfs(settings.input_dir)
    input_items = [item for item in input_items if Path(item["name"]).stem not in translated_stems and item["name"] not in seen]
    sort_order = config.get("sort_order", "smallest_first")
    if sort_order == "largest_first":
        input_items.sort(key=lambda item: item["size_mb"], reverse=True)
    elif sort_order == "custom":
        order_map = {name: index for index, name in enumerate(config.get("custom_order", []))}
        input_items.sort(key=lambda item: order_map.get(item["name"], 999999))
    else:
        input_items.sort(key=lambda item: item["size_mb"])
    for item in input_items:
        item["queued"] = False
    return items + input_items


def _legacy_ollama_status(settings: Settings) -> dict:
    try:
        with urllib.request.urlopen(f"{settings.llm_base_url.rstrip('/')}/api/tags", timeout=5) as response:
            data = json.loads(response.read())
        models = [
            {
                "name": item.get("name", ""),
                "size": item.get("size", 0),
                "modified_at": item.get("modified_at"),
            }
            for item in data.get("models", [])
        ]
        return {"connected": True, "models": models, "url": settings.llm_base_url}
    except Exception as exc:
        return {"connected": False, "models": [], "url": settings.llm_base_url, "error": str(exc)}


def _legacy_validations(settings: Settings) -> dict:
    validations = {}
    for path in settings.reports_dir.glob("*.relatorio.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = Path(str(report.get("source", path.stem))).name
        text_ok = bool(report.get("text_validation", {}).get("ok", False))
        structure_ok = bool(report.get("structural_validation", {}).get("ok", text_ok))
        visual_ok = bool(report.get("visual_validation", {}).get("ok", text_ok))
        passed = sum([text_ok, structure_ok, visual_ok])
        rate = int(round((passed / 3) * 100))
        validations[name] = {"result": "PASS" if rate >= 90 else "FAIL", "rate": rate}
    return validations


def _legacy_validation_for(settings: Settings, filename: str) -> dict:
    validations = _legacy_validations(settings)
    result = validations.get(filename, {"result": "FAIL", "rate": 0})
    return {"overall_pass": result["result"] == "PASS", "pass_rate": result["rate"] / 100}


def _list_pdfs(directory: Path, *, sort_mode: str = "name_asc", suffix: str | None = None) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    files = [path for path in directory.glob("*.pdf") if path.is_file()]
    if suffix:
        files = [path for path in files if path.name.endswith(suffix)]
    if sort_mode == "mtime_desc":
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    else:
        files.sort(key=lambda path: path.name.lower())
    return [
        {
            "name": path.name,
            "size_mb": _file_size_mb(path),
            "mtime": path.stat().st_mtime,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
        }
        for path in files
    ]


def _file_size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        return 0.0


def _elapsed_seconds(iso_value: str | None) -> float | None:
    if not iso_value:
        return None
    try:
        from datetime import datetime

        start = datetime.fromisoformat(iso_value.replace("Z", "+00:00")).timestamp()
        return max(0.0, time.time() - start)
    except Exception:
        return None


def _job_elapsed_seconds(job: dict | None) -> float | None:
    if not job:
        return None
    metadata = job.get("metadata", {}) or {}
    start = metadata.get("started_at") or job.get("created_at")
    end = metadata.get("finished_at") or (None if job.get("status") == JobStatus.RUNNING.value else job.get("updated_at"))
    start_ts = _iso_timestamp(start)
    end_ts = _iso_timestamp(end) if end else time.time()
    if start_ts is None or end_ts is None:
        return None
    return max(0.0, end_ts - start_ts)


def _iso_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, sec = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {sec:02d}s"
    return f"{sec}s"


def _finish_time(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    return time.strftime("%H:%M", time.localtime(time.time() + max(0, seconds)))


def _seconds_per_mb(jobs: list[dict]) -> float | None:
    values: list[float] = []
    for job in jobs:
        elapsed = _job_elapsed_seconds(job)
        size_mb = _file_size_mb(Path(job["source_path"]))
        if elapsed and size_mb > 0:
            values.append(elapsed / size_mb)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _aggregate_translation_metrics(jobs: list[dict]) -> dict:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "duration_seconds": 0.0}
    for job in jobs:
        metrics = (job.get("metadata", {}) or {}).get("translation_metrics", {}) or {}
        total["prompt_tokens"] += int(metrics.get("prompt_tokens") or 0)
        total["completion_tokens"] += int(metrics.get("completion_tokens") or 0)
        total["total_tokens"] += int(metrics.get("total_tokens") or 0)
        total["duration_seconds"] += float(metrics.get("duration_seconds") or 0.0)
    duration = float(total["duration_seconds"])
    total["tokens_per_second"] = round(total["completion_tokens"] / duration, 2) if duration > 0 else 0.0
    return total


def _book_timing(job: dict | None) -> dict:
    elapsed = _job_elapsed_seconds(job)
    return {"duration_sec": elapsed} if elapsed is not None else {}


def _book_tokens(job: dict | None) -> dict:
    if not job:
        return {}
    return dict((job.get("metadata", {}) or {}).get("translation_metrics", {}) or {})


def _source_stem_from_output(name: str) -> str:
    stem = Path(name).stem
    for suffix in [".traduzido", ".pesquisavel", ".original-pesquisavel", ".revisao", ".comparacao"]:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _safe_pdf_response(root: Path, filename: str, *, download: bool = False) -> FileResponse:
    name = Path(filename).name
    path = (root / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="PDF not found")
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/pdf",
        content_disposition_type="attachment" if download else "inline",
    )


app = create_app()
