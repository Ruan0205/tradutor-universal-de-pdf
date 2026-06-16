from pathlib import Path
import json
import os
import tempfile
import unittest

from translator.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_dashboard_config_overrides_runtime_model_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            (root / "dashboard_config.json").write_text(
                json.dumps(
                    {
                        "ollama_url": "http://ollama-cloud:11434",
                        "model_name": "cloud-rpg-model",
                        "image_text_mode": "google_translate_images",
                        "ollama_options": {"num_ctx": 65536, "num_gpu": -1, "temperature": 0.1},
                    }
                ),
                encoding="utf-8",
            )
            old_base = os.environ.get("BASE_DIR")
            try:
                os.environ["BASE_DIR"] = str(root)
                settings = load_settings()
            finally:
                if old_base is None:
                    os.environ.pop("BASE_DIR", None)
                else:
                    os.environ["BASE_DIR"] = old_base

            self.assertEqual(settings.llm_base_url, "http://ollama-cloud:11434")
            self.assertEqual(settings.llm_model, "cloud-rpg-model")
            self.assertEqual(settings.llm_context_tokens, 65536)
            self.assertEqual(settings.llm_num_gpu, -1)
            self.assertEqual(settings.llm_temperature, 0.1)
            self.assertEqual(settings.image_text_mode, "google_translate_images")


if __name__ == "__main__":
    unittest.main()
