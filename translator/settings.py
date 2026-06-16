from __future__ import annotations

from dataclasses import dataclass
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
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 3
    llm_max_output_tokens: Optional[int] = None
    llm_reasoning_mode: str = "off"
    ocr_provider: str = "auto"
    google_integration_enabled: bool = False
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


def load_settings() -> Settings:
    base_dir = Path(os.environ.get("BASE_DIR", "data"))
    password_file = os.environ.get("INITIAL_ADMIN_PASSWORD_FILE")
    return Settings(
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
        llm_temperature=float(os.environ.get("LLM_TEMPERATURE", "0.2") or 0.2),
        llm_timeout_seconds=_int_env("LLM_TIMEOUT_SECONDS", 300),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 3),
        llm_max_output_tokens=(
            _int_env("LLM_MAX_OUTPUT_TOKENS", 0)
            if os.environ.get("LLM_MAX_OUTPUT_TOKENS", "").strip()
            else None
        ),
        llm_reasoning_mode=os.environ.get("LLM_REASONING_MODE", "off").strip().lower() or "off",
        ocr_provider=os.environ.get("OCR_PROVIDER", "auto"),
        google_integration_enabled=_bool_env("GOOGLE_INTEGRATION_ENABLED", False),
        max_concurrent_books=_int_env("MAX_CONCURRENT_BOOKS", 1),
        max_memory_percent=_int_env("MAX_MEMORY_PERCENT", 85),
        min_free_disk_gb=_int_env("MIN_FREE_DISK_GB", 20),
    )
