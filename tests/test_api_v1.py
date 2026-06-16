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


if __name__ == "__main__":
    unittest.main()
