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

    def test_can_resubmit_completed_checksum_from_input_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            make_pdf(pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")

            first = store.submit_pdf(pdf)
            store.update_job(first["id"], status="completed")
            second = store.submit_pdf(pdf, reuse_existing=False)

            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(second["status"], "queued")

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

    def test_only_one_job_can_be_running_at_a_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_pdf = root / "first.pdf"
            second_pdf = root / "second.pdf"
            make_pdf(first_pdf)
            make_pdf(second_pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")
            first = store.submit_pdf(first_pdf)
            second = store.submit_pdf(second_pdf)

            claimed_first = store.claim_job(first["id"])
            claimed_second = store.claim_job(second["id"])
            claimed_next = store.claim_next_queued_job()

            self.assertEqual(claimed_first["status"], "running")
            self.assertTrue(store.has_running_job())
            self.assertIsNone(claimed_second)
            self.assertIsNone(claimed_next)

    def test_active_paused_job_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active_pdf = root / "active.pdf"
            waiting_pdf = root / "waiting.pdf"
            make_pdf(active_pdf)
            make_pdf(waiting_pdf)
            store = init_store(f"sqlite:///{root / 'jobs.db'}")
            active = store.submit_pdf(active_pdf)
            store.submit_pdf(waiting_pdf)

            store.update_job(active["id"], status="paused", current_stage="translation", current_page=12, total_pages=226)

            self.assertTrue(store.has_active_paused_job())


if __name__ == "__main__":
    unittest.main()
