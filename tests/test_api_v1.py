from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from translator.api import create_app, get_settings
from translator.settings import Settings


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


if __name__ == "__main__":
    unittest.main()
