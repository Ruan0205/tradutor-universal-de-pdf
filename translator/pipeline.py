from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import shutil
import time
from typing import Iterator

from engine.document_ir import (
    BBox,
    IRBlock,
    IRDocument,
    IRImage,
    IRPage,
    IRTextLine,
    Provenance,
    TextStyle,
    stable_id,
)

from .domain import JobStatus, PIPELINE_STAGES
from .providers import InferenceProvider, TranslationRequest
from .settings import Settings
from .store import JobStore


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PipelineRunner:
    def __init__(self, settings: Settings, store: JobStore, inference: InferenceProvider):
        self.settings = settings
        self.store = store
        self.inference = inference
        self.settings.ensure_dirs()

    def process_job(self, job_id: str) -> dict:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(f"Unknown job: {job_id}")
        source = Path(job["source_path"])
        job_dir = self.settings.work_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        self.store.update_job(
            job_id,
            status=JobStatus.RUNNING.value,
            provider=getattr(self.inference, "name", "unknown"),
            model=getattr(self.inference, "model", ""),
            error=None,
        )
        artifacts: dict[str, Path] = {}

        try:
            with self.stage(job_id, "global_analysis"):
                page_count = self._count_pages(source)
                self.store.update_job(job_id, total_pages=page_count, progress=8.0)

            with self.stage(job_id, "page_classification"):
                classification_path = job_dir / "page_classification.json"
                classifications = self._classify_pages(source)
                classification_path.write_text(json.dumps(classifications, indent=2), encoding="utf-8")
                artifacts["page_classification"] = classification_path
                self.store.add_artifact(job_id, "page_classification", classification_path)
                self.store.update_job(job_id, progress=16.0)

            with self.stage(job_id, "digital_extraction"):
                ir = self._build_ir(job, source, classifications)
                ir_path = job_dir / f"{source.stem}.ir.json"
                ir_path.write_text(ir.to_json(), encoding="utf-8")
                artifacts["document_ir"] = ir_path
                self.store.add_artifact(job_id, "document_ir", ir_path)
                self.store.update_job(job_id, progress=32.0)

            self._complete_noop_stages(
                job_id,
                [
                    "layout_analysis",
                    "selective_ocr",
                    "table_detection",
                    "image_text_detection",
                    "document_ir",
                    "terminology_extraction",
                    "glossary_initialization",
                    "semantic_segmentation",
                    "translation_planning",
                ],
            )

            with self.stage(job_id, "translation"):
                translated_ir = self._translate_ir(ir)
                translated_ir_path = job_dir / f"{source.stem}.translated.ir.json"
                translated_ir_path.write_text(translated_ir.to_json(), encoding="utf-8")
                artifacts["translated_ir"] = translated_ir_path
                self.store.add_artifact(job_id, "translated_ir", translated_ir_path)
                self.store.update_job(job_id, progress=58.0)

            self._complete_noop_stages(
                job_id,
                [
                    "linguistic_postprocess",
                    "table_reconstruction",
                    "image_reconstruction",
                    "page_composition",
                    "searchable_layer",
                ],
            )

            with self.stage(job_id, "pdf_generation"):
                translated_pdf = self.settings.output_dir / f"{source.stem}.traduzido.pdf"
                self._compose_translated_pdf(source, translated_ir, translated_pdf)
                artifacts["translated_pdf"] = translated_pdf
                self.store.add_artifact(job_id, "translated_pdf", translated_pdf)
                self.store.update_job(job_id, progress=74.0)

            with self.stage(job_id, "text_validation"):
                text_report = self._validate_text(translated_ir)
                text_report_path = job_dir / "text_validation.json"
                text_report_path.write_text(json.dumps(text_report, indent=2, ensure_ascii=False), encoding="utf-8")
                artifacts["text_validation"] = text_report_path
                self.store.add_artifact(job_id, "text_validation", text_report_path)

            with self.stage(job_id, "structural_validation"):
                structural_report = self._validate_structure(translated_ir)
                structural_report_path = job_dir / "structural_validation.json"
                structural_report_path.write_text(json.dumps(structural_report, indent=2, ensure_ascii=False), encoding="utf-8")
                artifacts["structural_validation"] = structural_report_path
                self.store.add_artifact(job_id, "structural_validation", structural_report_path)

            with self.stage(job_id, "visual_validation"):
                visual_report = self._validate_visual(translated_ir)
                visual_report_path = job_dir / "visual_validation.json"
                visual_report_path.write_text(json.dumps(visual_report, indent=2, ensure_ascii=False), encoding="utf-8")
                artifacts["visual_validation"] = visual_report_path
                self.store.add_artifact(job_id, "visual_validation", visual_report_path)

            needs_human_review = not (text_report["ok"] and structural_report["ok"] and visual_report["ok"])
            if needs_human_review:
                with self.stage(job_id, "auto_correction"):
                    correction_report = self._make_correction_report(text_report, structural_report, visual_report)
                    correction_report_path = job_dir / "auto_correction.json"
                    correction_report_path.write_text(json.dumps(correction_report, indent=2, ensure_ascii=False), encoding="utf-8")
                    artifacts["auto_correction"] = correction_report_path
                    self.store.add_artifact(job_id, "auto_correction", correction_report_path)
                with self.stage(job_id, "human_review"):
                    review_report = {
                        "ok": False,
                        "reason": "One or more validation checks require manual review.",
                        "text_validation": text_report,
                        "structural_validation": structural_report,
                        "visual_validation": visual_report,
                    }
                    review_report_path = job_dir / "human_review.json"
                    review_report_path.write_text(json.dumps(review_report, indent=2, ensure_ascii=False), encoding="utf-8")
                    artifacts["human_review"] = review_report_path
                    self.store.add_artifact(job_id, "human_review", review_report_path)
            else:
                self.store.set_stage_skipped(job_id, "auto_correction", reason="All validations passed")
                self.store.set_stage_skipped(job_id, "human_review", reason="All validations passed")

            with self.stage(job_id, "report_generation"):
                report_json = self.settings.reports_dir / f"{source.stem}.relatorio.json"
                report_html = self.settings.reports_dir / f"{source.stem}.relatorio.html"
                manifest = self.settings.reports_dir / f"{source.stem}.manifest.json"
                self._write_reports(
                    job_id,
                    job,
                    artifacts,
                    text_report,
                    structural_report,
                    visual_report,
                    report_json,
                    report_html,
                    manifest,
                )
                self.store.add_artifact(job_id, "report_json", report_json)
                self.store.add_artifact(job_id, "report_html", report_html)
                self.store.add_artifact(job_id, "manifest", manifest)
                artifacts["report_json"] = report_json
                artifacts["report_html"] = report_html
                artifacts["manifest"] = manifest
                self.store.update_job(job_id, progress=88.0)

            with self.stage(job_id, "publication"):
                originals_target = self.settings.originals_dir / source.name
                if source.resolve() != originals_target.resolve():
                    shutil.copy2(source, originals_target)
                self.store.add_artifact(job_id, "original_pdf", originals_target)

                searchable = self.settings.output_dir / f"{source.stem}.pesquisavel.pdf"
                original_searchable = self.settings.output_dir / f"{source.stem}.original-pesquisavel.pdf"
                review_pdf = self.settings.output_dir / f"{source.stem}.revisao.pdf"
                comparison_pdf = self.settings.output_dir / f"{source.stem}.comparacao.pdf"
                shutil.copy2(artifacts["translated_pdf"], searchable)
                shutil.copy2(originals_target, original_searchable)
                shutil.copy2(artifacts["translated_pdf"], review_pdf)
                self._create_comparison_pdf(originals_target, artifacts["translated_pdf"], comparison_pdf)
                for kind, path in [
                    ("searchable_pdf", searchable),
                    ("original_searchable_pdf", original_searchable),
                    ("review_pdf", review_pdf),
                    ("comparison_pdf", comparison_pdf),
                ]:
                    self.store.add_artifact(job_id, kind, path)
                self.store.update_job(job_id, progress=96.0)

            with self.stage(job_id, "output_sync"):
                sync_marker = job_dir / "sync.ready"
                sync_marker.write_text(now_iso(), encoding="utf-8")
                self.store.add_artifact(job_id, "sync_marker", sync_marker)

            final_job = self.store.update_job(
                job_id,
                status=JobStatus.NEEDS_REVIEW.value if needs_human_review else JobStatus.COMPLETED.value,
                current_stage="completed",
                progress=100.0,
            )
            return final_job
        except Exception as exc:
            self.store.update_job(job_id, status=JobStatus.FAILED.value, error=str(exc))
            raise

    @contextmanager
    def stage(self, job_id: str, name: str) -> Iterator[None]:
        start = time.perf_counter()
        self.store.set_stage_running(job_id, name)
        try:
            yield
        except Exception as exc:
            duration = int((time.perf_counter() - start) * 1000)
            self.store.set_stage_failed(job_id, name, str(exc), duration_ms=duration)
            raise
        duration = int((time.perf_counter() - start) * 1000)
        self.store.set_stage_completed(job_id, name, duration_ms=duration)

    def _complete_noop_stages(self, job_id: str, stage_names: list[str]) -> None:
        for name in stage_names:
            if name in PIPELINE_STAGES:
                self.store.set_stage_running(job_id, name)
                self.store.set_stage_completed(job_id, name)

    @staticmethod
    def _count_pages(path: Path) -> int:
        import fitz

        with fitz.open(str(path)) as doc:
            return doc.page_count

    @staticmethod
    def _classify_pages(path: Path) -> list[dict]:
        import fitz

        pages: list[dict] = []
        with fitz.open(str(path)) as doc:
            for index, page in enumerate(doc):
                text = page.get_text("text").strip()
                images = page.get_images(full=True)
                classification = []
                if text:
                    classification.append("digital")
                if images and not text:
                    classification.append("scanned")
                if images and text:
                    classification.append("hybrid")
                if not text and not images:
                    classification.append("blank")
                if page.rotation:
                    classification.append("rotated")
                pages.append(
                    {
                        "page_number": index + 1,
                        "classification": classification or ["digital"],
                        "text_chars": len(text),
                        "image_count": len(images),
                        "rotation": page.rotation,
                    }
                )
        return pages

    @staticmethod
    def _build_ir(job: dict, source: Path, classifications: list[dict]) -> IRDocument:
        import fitz

        class_by_page = {item["page_number"]: item["classification"] for item in classifications}
        pages: list[IRPage] = []
        with fitz.open(str(source)) as doc:
            for page_index, page in enumerate(doc):
                page_no = page_index + 1
                blocks: list[IRBlock] = []
                images: list[IRImage] = []
                page_dict = page.get_text("dict")
                for block_index, block in enumerate(page_dict.get("blocks", []), start=1):
                    bbox = BBox.from_any(block.get("bbox", [0, 0, 0, 0]))
                    if block.get("type") == 1:
                        images.append(
                            IRImage(
                                image_id=stable_id("page", page_no, "image", block_index),
                                bbox=bbox,
                                has_text=False,
                                provenance=[Provenance(source="pdf_image", tool="pymupdf")],
                            )
                        )
                        continue
                    if block.get("type") != 0:
                        continue
                    lines: list[IRTextLine] = []
                    text_parts: list[str] = []
                    for line_index, line in enumerate(block.get("lines", []), start=1):
                        spans = line.get("spans", [])
                        line_text = "".join(span.get("text", "") for span in spans).strip()
                        if not line_text:
                            continue
                        first_span = spans[0] if spans else {}
                        text_parts.append(line_text)
                        lines.append(
                            IRTextLine(
                                line_id=stable_id("page", page_no, "block", block_index, "line", line_index),
                                bbox=BBox.from_any(line.get("bbox", block.get("bbox", [0, 0, 0, 0]))),
                                original_text=line_text,
                                style=TextStyle(
                                    font_name=first_span.get("font"),
                                    font_size=first_span.get("size"),
                                    color=_color_to_rgb(first_span.get("color")),
                                ),
                                provenance=[Provenance(source="digital_text", tool="pymupdf", confidence=1.0)],
                            )
                        )
                    block_text = "\n".join(text_parts).strip()
                    if block_text:
                        blocks.append(
                            IRBlock(
                                block_id=stable_id("page", page_no, "block", block_index),
                                type="paragraph",
                                bbox=bbox,
                                lines=lines,
                                original_text=block_text,
                                source="digital_text",
                                reading_order=block_index,
                                status="extracted",
                                provenance=[Provenance(source="digital_text", tool="pymupdf", confidence=1.0)],
                            )
                        )
                pages.append(
                    IRPage(
                        page_id=stable_id("page", page_no),
                        page_number=page_no,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        rotation=int(page.rotation),
                        classification=class_by_page.get(page_no, ["digital"]),
                        blocks=blocks,
                        images=images,
                        provenance=[Provenance(source="pdf_page", tool="pymupdf")],
                    )
                )
        return IRDocument(
            document_id=job["id"],
            source_path=str(source),
            checksum=job["checksum"],
            pages=pages,
            source_language="en",
            target_language="pt-BR",
            title=source.stem,
            tool_versions={"pipeline": "3.0.0-rc.1"},
        )

    def _translate_ir(self, ir: IRDocument) -> IRDocument:
        glossary_terms = tuple(
            {
                "source": item["source_term"],
                "target": item["target_term"],
                "notes": item.get("notes", ""),
            }
            for item in self.store.list_glossary_terms()
        )
        for page in ir.pages:
            for block in page.blocks:
                if not block.original_text.strip():
                    continue
                cached = self.store.get_translation_memory(block.original_text)
                if cached:
                    block.translated_text = cached["translated_text"]
                    block.translation_provider = cached.get("provider") or "translation-memory"
                    block.translation_model = cached.get("model") or "cache"
                    block.translation_confidence = 1.0
                    block.status = "translated"
                    block.warnings.append("translation_memory_hit")
                    for line in block.lines:
                        line.translated_text = block.translated_text if len(block.lines) == 1 else None
                        line.translation_confidence = 1.0
                    continue

                result = self.inference.translate(
                    TranslationRequest(
                        block_id=block.block_id,
                        text=block.original_text,
                        glossary_terms=glossary_terms,
                    )
                )
                block.translated_text = result.translated_text
                block.translation_provider = result.provider
                block.translation_model = result.model
                block.translation_confidence = result.confidence
                block.status = "translated"
                block.warnings.extend(result.warnings)
                self.store.save_translation_memory(
                    block.original_text,
                    result.translated_text,
                    provider=result.provider,
                    model=result.model,
                )
                for line in block.lines:
                    line.translated_text = result.translated_text if len(block.lines) == 1 else None
                    line.translation_confidence = result.confidence
        ir.updated_at = now_iso()
        ir.history.append({"at": now_iso(), "event": "translated", "provider": self.inference.name, "model": self.inference.model})
        return ir

    @staticmethod
    def _compose_translated_pdf(source: Path, ir: IRDocument, output: Path) -> None:
        import fitz

        output.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(str(source)) as doc:
            for page_ir in ir.pages:
                page = doc[page_ir.page_number - 1]
                for block in page_ir.blocks:
                    if not block.translated_text or block.translated_text == block.original_text:
                        continue
                    rect = fitz.Rect(block.bbox.to_list())
                    if rect.is_empty or rect.width < 3 or rect.height < 3:
                        continue
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                for block in page_ir.blocks:
                    if not block.translated_text or block.translated_text == block.original_text:
                        continue
                    rect = fitz.Rect(block.bbox.to_list())
                    _insert_textbox_fit(page, rect, block.translated_text)
            doc.save(str(output), garbage=4, deflate=True)

    @staticmethod
    def _create_comparison_pdf(original: Path, translated: Path, output: Path) -> None:
        import fitz

        output.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(str(original)) as orig_doc, fitz.open(str(translated)) as trans_doc:
            out = fitz.open()
            count = min(orig_doc.page_count, trans_doc.page_count)
            for idx in range(count):
                left = orig_doc[idx].rect
                right = trans_doc[idx].rect
                width = left.width + right.width
                height = max(left.height, right.height)
                page = out.new_page(width=width, height=height)
                page.show_pdf_page(fitz.Rect(0, 0, left.width, left.height), orig_doc, idx)
                page.show_pdf_page(fitz.Rect(left.width, 0, width, right.height), trans_doc, idx)
            out.save(str(output), garbage=4, deflate=True)
            out.close()

    @staticmethod
    def _validate_text(ir: IRDocument) -> dict:
        blocks = [block for page in ir.pages for block in page.blocks if block.original_text.strip()]
        translated = [block for block in blocks if block.translated_text]
        needs_review = [
            block.block_id
            for block in translated
            if block.translation_confidence is not None and block.translation_confidence < 0.65
        ]
        return {
            "document_id": ir.document_id,
            "blocks_total": len(blocks),
            "blocks_translated": len(translated),
            "needs_review": needs_review,
            "ok": len(blocks) == len(translated) and not needs_review,
        }

    @staticmethod
    def _validate_structure(ir: IRDocument) -> dict:
        issues: list[dict] = []
        for page in ir.pages:
            if page.width <= 0 or page.height <= 0 or not math.isfinite(page.width + page.height):
                issues.append({"page": page.page_number, "type": "invalid_page_size"})
            for block in page.blocks:
                if not _bbox_inside_page(block.bbox, page.width, page.height):
                    issues.append(
                        {
                            "page": page.page_number,
                            "block_id": block.block_id,
                            "type": "block_outside_page",
                            "bbox": block.bbox.to_list(),
                        }
                    )
                for line in block.lines:
                    if not _bbox_inside_page(line.bbox, page.width, page.height):
                        issues.append(
                            {
                                "page": page.page_number,
                                "block_id": block.block_id,
                                "line_id": line.line_id,
                                "type": "line_outside_page",
                                "bbox": line.bbox.to_list(),
                            }
                        )
            for image in page.images:
                if not _bbox_inside_page(image.bbox, page.width, page.height):
                    issues.append(
                        {
                            "page": page.page_number,
                            "image_id": image.image_id,
                            "type": "image_outside_page",
                            "bbox": image.bbox.to_list(),
                        }
                    )
        return {
            "document_id": ir.document_id,
            "pages_total": len(ir.pages),
            "issues": issues,
            "ok": not issues,
        }

    @staticmethod
    def _validate_visual(ir: IRDocument) -> dict:
        issues: list[dict] = []
        for page in ir.pages:
            for block in page.blocks:
                if not block.translated_text:
                    continue
                bbox_area = max(1.0, _bbox_area(block.bbox))
                estimated_capacity = max(12, int(bbox_area / 18))
                if len(block.translated_text) > estimated_capacity * 2.2:
                    issues.append(
                        {
                            "page": page.page_number,
                            "block_id": block.block_id,
                            "type": "possible_text_overflow",
                            "chars": len(block.translated_text),
                            "estimated_capacity": estimated_capacity,
                        }
                    )
                for image in page.images:
                    if _bbox_intersects(block.bbox, image.bbox):
                        issues.append(
                            {
                                "page": page.page_number,
                                "block_id": block.block_id,
                                "image_id": image.image_id,
                                "type": "text_bbox_intersects_image",
                            }
                        )
        return {
            "document_id": ir.document_id,
            "issues": issues,
            "ok": not issues,
        }

    @staticmethod
    def _make_correction_report(text_report: dict, structural_report: dict, visual_report: dict) -> dict:
        return {
            "ok": False,
            "automatic_changes": [],
            "message": "Automatic correction is conservative in this RC; flagged pages are sent to review artifacts.",
            "text_validation": text_report,
            "structural_validation": structural_report,
            "visual_validation": visual_report,
        }

    @staticmethod
    def _write_reports(
        job_id: str,
        job: dict,
        artifacts: dict[str, Path],
        text_report: dict,
        structural_report: dict,
        visual_report: dict,
        report_json: Path,
        report_html: Path,
        manifest: Path,
    ) -> None:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        manifest_data = {
            "job_id": job_id,
            "source": job["source_path"],
            "checksum": job["checksum"],
            "generated_at": now_iso(),
            "artifacts": {name: str(path) for name, path in artifacts.items()},
            "text_validation": text_report,
            "structural_validation": structural_report,
            "visual_validation": visual_report,
        }
        report_json.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
        report_html.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><title>Relatorio</title></head>"
            "<body>"
            f"<h1>Relatorio do job {html.escape(job_id)}</h1>"
            f"<p>Status textual: {'OK' if text_report.get('ok') else 'Revisar'}</p>"
            f"<p>Status estrutural: {'OK' if structural_report.get('ok') else 'Revisar'}</p>"
            f"<p>Status visual: {'OK' if visual_report.get('ok') else 'Revisar'}</p>"
            f"<pre>{html.escape(json.dumps(manifest_data, indent=2, ensure_ascii=False))}</pre>"
            "</body></html>",
            encoding="utf-8",
        )


def _color_to_rgb(value) -> list[int] | None:
    if not isinstance(value, int):
        return None
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255]


def _fit_font_size(text: str, rect) -> float:
    chars = max(1, len(text))
    by_width = max(5.0, min(12.0, rect.width / max(8, chars / 1.8)))
    by_height = max(5.0, min(12.0, rect.height / 2.2))
    return min(by_width, by_height)


def _insert_textbox_fit(page, rect, text: str) -> float:
    import fitz

    start_size = _fit_font_size(text, rect)
    for step in range(0, 18):
        font_size = max(4.5, start_size - (step * 0.35))
        overflow = page.insert_textbox(
            rect,
            text,
            fontsize=font_size,
            fontname="helv",
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if overflow >= 0 or font_size <= 4.5:
            return font_size
    return 4.5


def _bbox_area(bbox: BBox) -> float:
    return max(0.0, bbox.x1 - bbox.x0) * max(0.0, bbox.y1 - bbox.y0)


def _bbox_inside_page(bbox: BBox, width: float, height: float, *, tolerance: float = 1.0) -> bool:
    values = [bbox.x0, bbox.y0, bbox.x1, bbox.y1, width, height]
    if not all(math.isfinite(value) for value in values):
        return False
    if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
        return False
    return (
        bbox.x0 >= -tolerance
        and bbox.y0 >= -tolerance
        and bbox.x1 <= width + tolerance
        and bbox.y1 <= height + tolerance
    )


def _bbox_intersects(left: BBox, right: BBox) -> bool:
    return not (
        left.x1 <= right.x0
        or right.x1 <= left.x0
        or left.y1 <= right.y0
        or right.y1 <= left.y0
    )
