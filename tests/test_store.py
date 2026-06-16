from pathlib import Path
import tempfile
import unittest

from reportlab.pdfgen import canvas

from translator.domain import PIPELINE_STAGES
from translator.store import init_store


def make_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "A short test document.")
    c.save()


class StoreTests(unittest.TestCase):
    def test_submit_creates_job_and_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            make_pdf(pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")

            job = store.submit_pdf(pdf)

            self.assertEqual(job["original_filename"], "sample.pdf")
            self.assertEqual(job["status"], "queued")
            self.assertEqual(len(store.list_stages(job["id"])), len(PIPELINE_STAGES))

    def test_duplicate_checksum_returns_existing_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            make_pdf(pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")

            first = store.submit_pdf(pdf)
            second = store.submit_pdf(pdf)

            self.assertEqual(first["id"], second["id"])

    def test_glossary_and_translation_memory_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")

            term = store.upsert_glossary_term("Armor Class", "Classe de Armadura", notes="D&D term")
            memory = store.save_translation_memory(
                "The rogue opens the lock.",
                "O ladino abre a fechadura.",
                provider="mock",
                model="mock",
            )

            self.assertEqual(term["target_term"], "Classe de Armadura")
            self.assertEqual(store.list_glossary_terms()[0]["source_term"], "Armor Class")
            self.assertEqual(memory["translated_text"], "O ladino abre a fechadura.")
            self.assertEqual(
                store.get_translation_memory("  The   rogue opens the lock. ")["translated_text"],
                "O ladino abre a fechadura.",
            )

    def test_claim_job_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            make_pdf(pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")
            job = store.submit_pdf(pdf)

            first = store.claim_job(job["id"])
            second = store.claim_job(job["id"])

            self.assertEqual(first["status"], "running")
            self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
