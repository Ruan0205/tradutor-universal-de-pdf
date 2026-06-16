from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
    update,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from sqlalchemy.pool import NullPool

from .domain import JobStatus, PIPELINE_STAGES, StageStatus


Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    source_path = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default=JobStatus.QUEUED.value)
    current_stage = Column(String(64), nullable=True)
    current_page = Column(Integer, nullable=False, default=0)
    total_pages = Column(Integer, nullable=False, default=0)
    progress = Column(Float, nullable=False, default=0.0)
    priority = Column(Integer, nullable=False, default=0)
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    stages = relationship("StageRecord", back_populates="job", cascade="all, delete-orphan")
    artifacts = relationship("ArtifactRecord", back_populates="job", cascade="all, delete-orphan")


class StageRecord(Base):
    __tablename__ = "job_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default=StageStatus.PENDING.value)
    attempt = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    artifact_path = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    job = relationship("JobRecord", back_populates="stages")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    kind = Column(String(64), nullable=False)
    path = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    job = relationship("JobRecord", back_populates="artifacts")


class GlossaryTermRecord(Base):
    __tablename__ = "glossary_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_term = Column(Text, nullable=False, unique=True)
    target_term = Column(Text, nullable=False)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class TranslationMemoryRecord(Base):
    __tablename__ = "translation_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_hash = Column(String(64), nullable=False, unique=True)
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


def make_engine(database_url: str):
    kwargs: Dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = NullPool
    return create_engine(database_url, future=True, **kwargs)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class JobStore:
    def __init__(self, database_url: str):
        self.engine = make_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.SessionLocal()

    def submit_pdf(self, source_path: Path, *, priority: int = 0, metadata: Optional[dict] = None) -> Dict[str, Any]:
        source_path = source_path.resolve()
        checksum = sha256_file(source_path)
        with self.session() as session:
            existing = session.execute(
                select(JobRecord).where(JobRecord.checksum == checksum).order_by(JobRecord.created_at.desc())
            ).scalars().first()
            if existing:
                return self.to_dict(existing)

            job = JobRecord(
                id=str(uuid.uuid4()),
                source_path=str(source_path),
                original_filename=source_path.name,
                checksum=checksum,
                status=JobStatus.QUEUED.value,
                priority=priority,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            session.add(job)
            for stage_name in PIPELINE_STAGES:
                session.add(StageRecord(job_id=job.id, name=stage_name, status=StageStatus.PENDING.value))
            session.commit()
            return self.to_dict(job)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as session:
            job = session.get(JobRecord, job_id)
            return self.to_dict(job) if job else None

    def list_jobs(self, *, limit: int = 100) -> list[Dict[str, Any]]:
        with self.session() as session:
            rows = session.execute(
                select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)
            ).scalars().all()
            return [self.to_dict(row) for row in rows]

    def next_queued_job(self) -> Optional[Dict[str, Any]]:
        with self.session() as session:
            job = session.execute(
                select(JobRecord)
                .where(JobRecord.status == JobStatus.QUEUED.value)
                .order_by(JobRecord.priority.desc(), JobRecord.created_at.asc())
            ).scalars().first()
            return self.to_dict(job) if job else None

    def claim_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as session:
            result = session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == JobStatus.QUEUED.value)
                .values(status=JobStatus.RUNNING.value, current_stage="queued", updated_at=utcnow())
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            job = session.get(JobRecord, job_id)
            return self.to_dict(job) if job else None

    def claim_next_queued_job(self) -> Optional[Dict[str, Any]]:
        candidate = self.next_queued_job()
        if not candidate:
            return None
        claimed = self.claim_job(candidate["id"])
        if claimed and claimed["status"] == JobStatus.RUNNING.value:
            return claimed
        return None

    def update_job(self, job_id: str, **fields: Any) -> Dict[str, Any]:
        with self.session() as session:
            job = session.get(JobRecord, job_id)
            if not job:
                raise KeyError(f"Unknown job: {job_id}")
            for key, value in fields.items():
                if key == "metadata" and isinstance(value, dict):
                    setattr(job, "metadata_json", json.dumps(value, ensure_ascii=False))
                elif hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = utcnow()
            session.commit()
            return self.to_dict(job)

    def set_stage_running(self, job_id: str, name: str) -> None:
        with self.session() as session:
            stage = self._stage(session, job_id, name)
            stage.status = StageStatus.RUNNING.value
            stage.attempt += 1
            stage.started_at = utcnow()
            stage.error = None
            job = session.get(JobRecord, job_id)
            if job:
                job.current_stage = name
                job.updated_at = utcnow()
            session.commit()

    def set_stage_completed(self, job_id: str, name: str, *, duration_ms: int = 0, artifact_path: Optional[Path] = None) -> None:
        with self.session() as session:
            stage = self._stage(session, job_id, name)
            stage.status = StageStatus.COMPLETED.value
            stage.duration_ms = duration_ms
            stage.finished_at = utcnow()
            if artifact_path:
                stage.artifact_path = str(artifact_path)
            session.commit()

    def set_stage_skipped(self, job_id: str, name: str, *, reason: str = "") -> None:
        with self.session() as session:
            stage = self._stage(session, job_id, name)
            stage.status = StageStatus.SKIPPED.value
            stage.error = reason or None
            stage.started_at = stage.started_at or utcnow()
            stage.finished_at = utcnow()
            job = session.get(JobRecord, job_id)
            if job:
                job.current_stage = name
                job.updated_at = utcnow()
            session.commit()

    def set_stage_failed(self, job_id: str, name: str, error: str, *, duration_ms: int = 0) -> None:
        with self.session() as session:
            stage = self._stage(session, job_id, name)
            stage.status = StageStatus.FAILED.value
            stage.duration_ms = duration_ms
            stage.error = error
            stage.finished_at = utcnow()
            job = session.get(JobRecord, job_id)
            if job:
                job.status = JobStatus.FAILED.value
                job.error = error
                job.updated_at = utcnow()
            session.commit()

    def add_artifact(self, job_id: str, kind: str, path: Path) -> Dict[str, Any]:
        checksum = sha256_file(path) if path.exists() and path.is_file() else None
        with self.session() as session:
            artifact = ArtifactRecord(job_id=job_id, kind=kind, path=str(path), checksum=checksum)
            session.add(artifact)
            session.commit()
            return {
                "id": artifact.id,
                "job_id": artifact.job_id,
                "kind": artifact.kind,
                "path": artifact.path,
                "checksum": artifact.checksum,
            }

    def get_artifact(self, artifact_id: int) -> Optional[Dict[str, Any]]:
        with self.session() as session:
            row = session.get(ArtifactRecord, artifact_id)
            if not row:
                return None
            return {
                "id": row.id,
                "job_id": row.job_id,
                "kind": row.kind,
                "path": row.path,
                "checksum": row.checksum,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def list_artifacts(self, job_id: str) -> list[Dict[str, Any]]:
        with self.session() as session:
            rows = session.execute(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id)).scalars().all()
            return [
                {
                    "id": row.id,
                    "job_id": row.job_id,
                    "kind": row.kind,
                    "path": row.path,
                    "checksum": row.checksum,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def list_glossary_terms(self) -> list[Dict[str, Any]]:
        with self.session() as session:
            rows = session.execute(select(GlossaryTermRecord).order_by(GlossaryTermRecord.source_term.asc())).scalars().all()
            return [
                {
                    "id": row.id,
                    "source_term": row.source_term,
                    "target_term": row.target_term,
                    "notes": row.notes,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def upsert_glossary_term(self, source_term: str, target_term: str, *, notes: str = "") -> Dict[str, Any]:
        source_term = source_term.strip()
        target_term = target_term.strip()
        if not source_term or not target_term:
            raise ValueError("Glossary terms require source_term and target_term")
        with self.session() as session:
            row = session.execute(
                select(GlossaryTermRecord).where(GlossaryTermRecord.source_term == source_term)
            ).scalars().first()
            if row:
                row.target_term = target_term
                row.notes = notes
            else:
                row = GlossaryTermRecord(source_term=source_term, target_term=target_term, notes=notes)
                session.add(row)
            session.commit()
            return {
                "id": row.id,
                "source_term": row.source_term,
                "target_term": row.target_term,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def get_translation_memory(self, source_text: str) -> Optional[Dict[str, Any]]:
        source_hash = _source_hash(source_text)
        with self.session() as session:
            row = session.execute(
                select(TranslationMemoryRecord).where(TranslationMemoryRecord.source_hash == source_hash)
            ).scalars().first()
            if not row:
                return None
            return {
                "id": row.id,
                "source_hash": row.source_hash,
                "source_text": row.source_text,
                "translated_text": row.translated_text,
                "provider": row.provider,
                "model": row.model,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def save_translation_memory(
        self,
        source_text: str,
        translated_text: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        source_hash = _source_hash(source_text)
        with self.session() as session:
            row = session.execute(
                select(TranslationMemoryRecord).where(TranslationMemoryRecord.source_hash == source_hash)
            ).scalars().first()
            if row:
                row.translated_text = translated_text
                row.provider = provider
                row.model = model
            else:
                row = TranslationMemoryRecord(
                    source_hash=source_hash,
                    source_text=source_text,
                    translated_text=translated_text,
                    provider=provider,
                    model=model,
                )
                session.add(row)
            session.commit()
            return {
                "id": row.id,
                "source_hash": row.source_hash,
                "source_text": row.source_text,
                "translated_text": row.translated_text,
                "provider": row.provider,
                "model": row.model,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def list_stages(self, job_id: str) -> list[Dict[str, Any]]:
        with self.session() as session:
            rows = session.execute(select(StageRecord).where(StageRecord.job_id == job_id)).scalars().all()
            return [
                {
                    "name": row.name,
                    "status": row.status,
                    "attempt": row.attempt,
                    "duration_ms": row.duration_ms,
                    "error": row.error,
                    "artifact_path": row.artifact_path,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]

    @staticmethod
    def to_dict(job: JobRecord) -> Dict[str, Any]:
        return {
            "id": job.id,
            "source_path": job.source_path,
            "original_filename": job.original_filename,
            "checksum": job.checksum,
            "status": job.status,
            "current_stage": job.current_stage,
            "current_page": job.current_page,
            "total_pages": job.total_pages,
            "progress": job.progress,
            "priority": job.priority,
            "provider": job.provider,
            "model": job.model,
            "error": job.error,
            "metadata": json.loads(job.metadata_json or "{}"),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    @staticmethod
    def _stage(session: Session, job_id: str, name: str) -> StageRecord:
        stage = session.execute(
            select(StageRecord).where(StageRecord.job_id == job_id, StageRecord.name == name)
        ).scalars().first()
        if not stage:
            raise KeyError(f"Unknown stage {name!r} for job {job_id}")
        return stage


def _source_hash(text: str) -> str:
    normalized = " ".join(text.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def init_store(database_url: str) -> JobStore:
    store = JobStore(database_url)
    store.initialize()
    return store
