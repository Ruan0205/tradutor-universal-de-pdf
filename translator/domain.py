from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


PIPELINE_STAGES = [
    "receive",
    "stability_check",
    "security_validation",
    "checksum",
    "register_job",
    "global_analysis",
    "page_classification",
    "digital_extraction",
    "layout_analysis",
    "selective_ocr",
    "table_detection",
    "image_text_detection",
    "document_ir",
    "terminology_extraction",
    "glossary_initialization",
    "semantic_segmentation",
    "translation_planning",
    "translation",
    "linguistic_postprocess",
    "table_reconstruction",
    "image_reconstruction",
    "page_composition",
    "searchable_layer",
    "pdf_generation",
    "text_validation",
    "structural_validation",
    "visual_validation",
    "auto_correction",
    "human_review",
    "report_generation",
    "publication",
    "output_sync",
]
