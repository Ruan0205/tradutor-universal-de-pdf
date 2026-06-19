from pathlib import Path
import io
import tempfile
import unittest

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from engine.document_ir import BBox, IRBlock, IRDocument, IRPage
from translator.pipeline import PipelineRunner, _should_translate_block_text
from translator.providers import MockProvider
from translator.settings import Settings
from translator.store import init_store


def make_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "The wizard casts a spell.")
    c.drawString(72, 700, "The target takes damage.")
    c.save()


def make_hybrid_pdf(path: Path) -> None:
    image = Image.new("RGB", (80, 40), color=(240, 240, 240))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "The wizard casts a spell.")
    c.drawImage(ImageReader(buffer), 72, 640, width=120, height=60)
    c.save()


class FakeImageProvider:
    def __init__(self):
        self.calls = 0

    def translate_image_bytes(self, image_bytes: bytes, source_lang: str, target_lang: str):
        self.calls += 1
        image = Image.new("RGB", (80, 40), color=(10, 120, 200))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        class Result:
            image_bytes = buffer.getvalue()

        return Result()


class PipelineRunnerTests(unittest.TestCase):
    def test_process_job_generates_core_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "book.pdf"
            make_pdf(pdf)
            settings = Settings(
                base_dir=root / "data",
                database_url=f"sqlite:///{root / 'jobs.db'}",
                llm_provider="mock",
            )
            settings.ensure_dirs()
            store = init_store(settings.database_url)
            job = store.submit_pdf(pdf)

            result = PipelineRunner(settings, store, MockProvider()).process_job(job["id"])
            artifacts = store.list_artifacts(job["id"])
            kinds = {item["kind"] for item in artifacts}

            self.assertEqual(result["status"], "completed")
            self.assertIn("document_ir", kinds)
            self.assertIn("translated_pdf", kinds)
            self.assertIn("structural_validation", kinds)
            self.assertIn("visual_validation", kinds)
            self.assertIn("manifest", kinds)
            self.assertTrue((settings.output_dir / "book.traduzido.pdf").exists())
            self.assertEqual([path.name for path in settings.output_dir.glob("*.pdf")], ["book.traduzido.pdf"])

    def test_google_translate_images_runs_for_hybrid_pdf_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "hybrid.pdf"
            make_hybrid_pdf(pdf)
            settings = Settings(
                base_dir=root / "data",
                database_url=f"sqlite:///{root / 'jobs.db'}",
                llm_provider="mock",
                image_text_mode="google_translate_images",
                google_integration_enabled=True,
            )
            settings.ensure_dirs()
            store = init_store(settings.database_url)
            job = store.submit_pdf(pdf)
            runner = PipelineRunner(settings, store, MockProvider())
            fake_images = FakeImageProvider()
            runner.google_images = fake_images

            result = runner.process_job(job["id"])

            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(fake_images.calls, 1)

    def test_text_validation_rejects_document_without_blocks(self):
        ir = IRDocument(
            document_id="empty",
            source_path="empty.pdf",
            checksum="abc",
            pages=[
                IRPage(
                    page_id="page-1",
                    page_number=1,
                    width=100,
                    height=100,
                    classification=["scanned"],
                    blocks=[],
                )
            ],
        )

        report = PipelineRunner._validate_text(ir)

        self.assertFalse(report["ok"])
        self.assertEqual(report["blocks_total"], 0)
        self.assertEqual(report["issues"][0]["type"], "no_text_blocks")

    def test_text_validation_rejects_unchanged_translation(self):
        ir = IRDocument(
            document_id="unchanged",
            source_path="book.pdf",
            checksum="abc",
            pages=[
                IRPage(
                    page_id="page-1",
                    page_number=1,
                    width=100,
                    height=100,
                    classification=["digital"],
                    blocks=[
                        IRBlock(
                            block_id="b1",
                            type="paragraph",
                            bbox=BBox(1, 1, 90, 20),
                            original_text="The spell deals fire damage to the creature.",
                            translated_text="The spell deals fire damage to the creature.",
                        )
                    ],
                )
            ],
        )

        report = PipelineRunner._validate_text(ir)

        self.assertFalse(report["ok"])
        self.assertEqual(report["unchanged_blocks"], 1)

    def test_ocr_noise_is_not_sent_to_translation(self):
        self.assertFalse(_should_translate_block_text("LLY A. gsag Po a4 its aff Gee ARsa fCb wage Kee eee"))
        self.assertTrue(_should_translate_block_text("Armor Class 18 Hit Points 120 The creature makes two attacks."))


if __name__ == "__main__":
    unittest.main()
