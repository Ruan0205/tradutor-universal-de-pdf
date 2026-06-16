from pathlib import Path
import tempfile
import unittest

from reportlab.pdfgen import canvas

from translator.pipeline import PipelineRunner
from translator.providers import MockProvider
from translator.settings import Settings
from translator.store import init_store


def make_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "The wizard casts a spell.")
    c.drawString(72, 700, "The target takes damage.")
    c.save()


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


if __name__ == "__main__":
    unittest.main()
