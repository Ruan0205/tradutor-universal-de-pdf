from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from translator.api import create_app, get_settings
from translator.domain import JobStatus
from translator.settings import Settings
from translator.store import init_store


def make_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "The rogue opens the lock.")
    c.save()


class ApiV1Tests(unittest.TestCase):
    def test_health_and_submit_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "api.pdf"
            make_pdf(pdf)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}", llm_provider="mock")
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            health = client.get("/api/v1/health")
            submitted = client.post("/api/v1/jobs", json={"path": str(pdf), "authorized": True})

            self.assertEqual(health.status_code, 200)
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["original_filename"], "api.pdf")

    def test_dashboard_requires_auth_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                base_dir=root / "data",
                database_url=f"sqlite:///{root / 'api.db'}",
                auth_enabled=True,
                initial_admin_user="admin",
                initial_admin_password="secret",
            )
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            health = client.get("/api/v1/health")
            anonymous = client.get("/")
            authenticated = client.get("/", auth=("admin", "secret"))

            self.assertEqual(health.status_code, 200)
            self.assertEqual(anonymous.status_code, 401)
            self.assertEqual(authenticated.status_code, 200)
            self.assertIn("Dashboard", authenticated.text)

    def test_glossary_api_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}")
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            created = client.post(
                "/api/v1/glossaries",
                json={"source_term": "Armor Class", "target_term": "Classe de Armadura", "notes": "D&D"},
            )
            listed = client.get("/api/v1/glossaries")

            self.assertEqual(created.status_code, 200)
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["terms"][0]["target_term"], "Classe de Armadura")

    def test_legacy_status_lists_only_final_translated_pdfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}")
            settings.ensure_dirs()
            for name in [
                "book.traduzido.pdf",
                "book.revisao.pdf",
                "book.comparacao.pdf",
                "book.pesquisavel.pdf",
            ]:
                make_pdf(settings.output_dir / name)
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            response = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            translated = response.json()["books"]["translated"]
            self.assertEqual([item["name"] for item in translated], ["book.traduzido.pdf"])
            self.assertEqual(response.json()["books"]["counts"]["translated"], 1)

    def test_legacy_queue_next_and_order_control_untranslated_books(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}", job_dispatcher="manual")
            settings.ensure_dirs()
            first = settings.input_dir / "first.pdf"
            second = settings.input_dir / "second.pdf"
            third = settings.input_dir / "third.pdf"
            make_pdf(first)
            make_pdf(second)
            make_pdf(third)
            store = init_store(settings.database_url)
            store.submit_pdf(first)
            store.submit_pdf(second)
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            next_response = client.post("/api/queue/next", json={"filename": "second.pdf"})
            status_after_next = client.get("/api/status").json()
            order_response = client.post("/api/queue/order", json={"order": ["first.pdf", "second.pdf"]})
            status_after_order = client.get("/api/status").json()
            unqueued_next_response = client.post("/api/queue/next", json={"filename": "third.pdf"})
            status_after_unqueued_next = client.get("/api/status").json()

            self.assertEqual(next_response.status_code, 200)
            self.assertEqual(status_after_next["books"]["input"][0]["name"], "second.pdf")
            self.assertEqual(order_response.status_code, 200)
            self.assertEqual([item["name"] for item in status_after_order["books"]["input"][:2]], ["first.pdf", "second.pdf"])
            self.assertEqual(unqueued_next_response.status_code, 200)
            self.assertEqual(status_after_unqueued_next["books"]["input"][0]["name"], "third.pdf")
            self.assertEqual(status_after_order["books"]["counts"]["untranslated"], 3)

    def test_legacy_start_requeues_cancelled_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}", job_dispatcher="manual")
            settings.ensure_dirs()
            pdf = settings.input_dir / "restart-me.pdf"
            make_pdf(pdf)
            store = init_store(settings.database_url)
            job = store.submit_pdf(pdf)
            store.update_job(job["id"], status=JobStatus.CANCELLED.value, error="stopped")
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            response = client.post("/api/start")
            refreshed = store.get_job(job["id"])

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])
            self.assertEqual(refreshed["status"], JobStatus.QUEUED.value)
            self.assertIsNone(refreshed["error"])
            self.assertEqual(response.json()["restarted"][0]["name"], "restart-me.pdf")

    def test_legacy_start_refuses_unavailable_ollama_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                base_dir=root / "data",
                database_url=f"sqlite:///{root / 'api.db'}",
                job_dispatcher="manual",
                llm_provider="ollama",
                llm_model="missing-model",
                llm_base_url="http://127.0.0.1:9",
            )
            settings.ensure_dirs()
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            response = client.post("/api/start")

            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["ok"])
            self.assertIn("Ollama", response.json()["error"])

    def test_legacy_status_prefers_paused_job_with_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}", job_dispatcher="manual")
            settings.ensure_dirs()
            active_pdf = settings.input_dir / "MonsterManualV.pdf"
            other_pdf = settings.input_dir / "other.pdf"
            make_pdf(active_pdf)
            make_pdf(other_pdf)
            store = init_store(settings.database_url)
            active = store.submit_pdf(active_pdf)
            other = store.submit_pdf(other_pdf)
            store.update_job(
                active["id"],
                status=JobStatus.PAUSED.value,
                current_stage="translation",
                current_page=27,
                total_pages=226,
            )
            store.update_job(other["id"], status=JobStatus.PAUSED.value)
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            response = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["state"]["current_book"]["filename"], "MonsterManualV.pdf")
            self.assertEqual(response.json()["state"]["current_page"], 27)

    def test_legacy_pause_and_resume_affect_only_active_book(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(base_dir=root / "data", database_url=f"sqlite:///{root / 'api.db'}", job_dispatcher="manual")
            settings.ensure_dirs()
            active_pdf = settings.input_dir / "active.pdf"
            queued_pdf = settings.input_dir / "queued.pdf"
            make_pdf(active_pdf)
            make_pdf(queued_pdf)
            store = init_store(settings.database_url)
            active = store.submit_pdf(active_pdf)
            queued = store.submit_pdf(queued_pdf)
            store.update_job(active["id"], status=JobStatus.RUNNING.value, current_stage="translation", current_page=3)
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)

            paused = client.post("/api/pause")
            active_after_pause = store.get_job(active["id"])
            queued_after_pause = store.get_job(queued["id"])
            resumed = client.post("/api/resume")
            active_after_resume = store.get_job(active["id"])
            queued_after_resume = store.get_job(queued["id"])

            self.assertEqual(paused.status_code, 200)
            self.assertEqual(len(paused.json()["jobs"]), 1)
            self.assertEqual(active_after_pause["status"], JobStatus.PAUSED.value)
            self.assertEqual(queued_after_pause["status"], JobStatus.QUEUED.value)
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(len(resumed.json()["jobs"]), 1)
            self.assertEqual(active_after_resume["status"], JobStatus.QUEUED.value)
            self.assertEqual(queued_after_resume["status"], JobStatus.QUEUED.value)


if __name__ == "__main__":
    unittest.main()
