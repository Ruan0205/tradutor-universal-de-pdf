from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Optional


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8050
    base_dir: Path = Path("data")
    database_url: str = "sqlite:///data/translator.db"
    redis_url: str = "redis://localhost:6379/0"
    auth_enabled: bool = False
    initial_admin_user: str = "admin"
    initial_admin_password: Optional[str] = None
    initial_admin_password_file: Optional[Path] = None
    llm_provider: str = "mock"
    llm_model: str = "qwen3.5:9b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: Optional[str] = None
    llm_api_key_file: Optional[Path] = None
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 3
    llm_max_output_tokens: Optional[int] = None
    llm_context_tokens: Optional[int] = 32768
    llm_num_gpu: Optional[int] = 0
    llm_num_thread: Optional[int] = 4
    llm_keep_alive: Optional[str] = "24h"
    llm_reasoning_mode: str = "off"
    job_dispatcher: str = "inline"
    watch_stability_seconds: float = 2.0
    image_text_mode: str = "google_translate_images"
    ocr_provider: str = "auto"
    google_integration_enabled: bool = True
    max_concurrent_books: int = 1
    max_memory_percent: int = 85
    min_free_disk_gb: int = 20

    @property
    def input_dir(self) -> Path:
        return Path(os.environ.get("INPUT_DIR", str(self.base_dir / "input")))

    @property
    def work_dir(self) -> Path:
        return Path(os.environ.get("WORK_DIR", str(self.base_dir / "work")))

    @property
    def output_dir(self) -> Path:
        return Path(os.environ.get("OUTPUT_DIR", str(self.base_dir / "output")))

    @property
    def originals_dir(self) -> Path:
        return Path(os.environ.get("ORIGINALS_DIR", str(self.base_dir / "originals")))

    @property
    def reports_dir(self) -> Path:
        return Path(os.environ.get("REPORTS_DIR", str(self.base_dir / "reports")))

    @property
    def backup_dir(self) -> Path:
        return Path(os.environ.get("BACKUP_DIR", str(self.base_dir / "backups")))

    def ensure_dirs(self) -> None:
        for path in [
            self.base_dir,
            self.input_dir,
            self.work_dir,
            self.output_dir,
            self.originals_dir,
            self.reports_dir,
            self.backup_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def admin_password(self) -> Optional[str]:
        if self.initial_admin_password:
            return self.initial_admin_password
        if self.initial_admin_password_file and self.initial_admin_password_file.exists():
            return self.initial_admin_password_file.read_text(encoding="utf-8").strip()
        return None

    def api_key(self) -> Optional[str]:
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_api_key_file and self.llm_api_key_file.exists():
            return self.llm_api_key_file.read_text(encoding="utf-8").strip()
        return None


def load_settings() -> Settings:
    base_dir = Path(os.environ.get("BASE_DIR", "data"))
    password_file = os.environ.get("INITIAL_ADMIN_PASSWORD_FILE")
    llm_api_key_file = os.environ.get("LLM_API_KEY_FILE")
    settings = Settings(
        app_env=os.environ.get("APP_ENV", "development"),
        host=os.environ.get("APP_HOST", "0.0.0.0"),
        port=_int_env("APP_PORT", 8050),
        base_dir=base_dir,
        database_url=os.environ.get("DATABASE_URL", f"sqlite:///{base_dir / 'translator.db'}"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        auth_enabled=_bool_env("AUTH_ENABLED", False),
        initial_admin_user=os.environ.get("INITIAL_ADMIN_USER", "admin"),
        initial_admin_password=os.environ.get("INITIAL_ADMIN_PASSWORD"),
        initial_admin_password_file=Path(password_file) if password_file else None,
        llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
        llm_model=os.environ.get("LLM_MODEL", "qwen3.5:9b"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434"),
        llm_api_key=os.environ.get("LLM_API_KEY"),
        llm_api_key_file=Path(llm_api_key_file) if llm_api_key_file else None,
        llm_temperature=float(os.environ.get("LLM_TEMPERATURE", "0.2") or 0.2),
        llm_timeout_seconds=_int_env("LLM_TIMEOUT_SECONDS", 300),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 3),
        llm_max_output_tokens=(
            _int_env("LLM_MAX_OUTPUT_TOKENS", 0)
            if os.environ.get("LLM_MAX_OUTPUT_TOKENS", "").strip()
            else None
        ),
        llm_context_tokens=(
            _int_env("LLM_CONTEXT_TOKENS", 32768)
            if os.environ.get("LLM_CONTEXT_TOKENS", "").strip()
            else 32768
        ),
        llm_num_gpu=(
            _int_env("LLM_NUM_GPU", 0)
            if os.environ.get("LLM_NUM_GPU", "").strip()
            else 0
        ),
        llm_num_thread=(
            _int_env("LLM_NUM_THREAD", 4)
            if os.environ.get("LLM_NUM_THREAD", "").strip()
            else 4
        ),
        llm_keep_alive=os.environ.get("LLM_KEEP_ALIVE", "24h").strip() or None,
        llm_reasoning_mode=os.environ.get("LLM_REASONING_MODE", "off").strip().lower() or "off",
        job_dispatcher=os.environ.get("JOB_DISPATCHER", "inline").strip().lower() or "inline",
        watch_stability_seconds=float(os.environ.get("WATCH_STABILITY_SECONDS", "2.0") or 2.0),
        image_text_mode=(
            os.environ.get("IMAGE_TEXT_MODE", "google_translate_images").strip().lower()
            or "google_translate_images"
        ),
        ocr_provider=os.environ.get("OCR_PROVIDER", "auto"),
        google_integration_enabled=_bool_env("GOOGLE_INTEGRATION_ENABLED", True),
        max_concurrent_books=_int_env("MAX_CONCURRENT_BOOKS", 1),
        max_memory_percent=_int_env("MAX_MEMORY_PERCENT", 85),
        min_free_disk_gb=_int_env("MIN_FREE_DISK_GB", 20),
    )
    return _apply_dashboard_config(settings)


def _apply_dashboard_config(settings: Settings) -> Settings:
    path = settings.base_dir / "dashboard_config.json"
    if not path.exists():
        return settings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return settings

    options = data.get("ollama_options", {}) or {}
    updates = {}
    if data.get("ollama_url"):
        updates["llm_base_url"] = str(data["ollama_url"]).strip()
    if data.get("model_name"):
        updates["llm_model"] = str(data["model_name"]).strip()
    if data.get("image_text_mode"):
        updates["image_text_mode"] = str(data["image_text_mode"]).strip().lower()
    if "temperature" in options:
        updates["llm_temperature"] = float(options["temperature"])
    if "num_ctx" in options and str(options["num_ctx"]).strip():
        updates["llm_context_tokens"] = int(options["num_ctx"])
    if "num_gpu" in options and str(options["num_gpu"]).strip():
        updates["llm_num_gpu"] = int(options["num_gpu"])
    if "num_thread" in options and str(options["num_thread"]).strip():
        updates["llm_num_thread"] = int(options["num_thread"])
    if "num_predict" in options and str(options["num_predict"]).strip():
        updates["llm_max_output_tokens"] = int(options["num_predict"])
    return replace(settings, **updates) if updates else settings
