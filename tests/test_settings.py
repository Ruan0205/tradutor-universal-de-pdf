from pathlib import Path
import json
import os
import tempfile
import unittest

from translator.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_google_translate_images_is_default_image_mode(self):
        old_mode = os.environ.get("IMAGE_TEXT_MODE")
        old_base = os.environ.get("BASE_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.environ.pop("IMAGE_TEXT_MODE", None)
                os.environ["BASE_DIR"] = tmp
                settings = load_settings()
            finally:
                if old_mode is None:
                    os.environ.pop("IMAGE_TEXT_MODE", None)
                else:
                    os.environ["IMAGE_TEXT_MODE"] = old_mode
                if old_base is None:
                    os.environ.pop("BASE_DIR", None)
                else:
                    os.environ["BASE_DIR"] = old_base

        self.assertEqual(settings.image_text_mode, "google_translate_images")

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

    def test_llm_api_key_can_be_loaded_from_file(self):
        old_file = os.environ.get("LLM_API_KEY_FILE")
        old_key = os.environ.get("LLM_API_KEY")
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "key"
            key_file.write_text("secret-token\n", encoding="utf-8")
            try:
                os.environ.pop("LLM_API_KEY", None)
                os.environ["LLM_API_KEY_FILE"] = str(key_file)
                settings = load_settings()
                self.assertEqual(settings.api_key(), "secret-token")
            finally:
                if old_file is None:
                    os.environ.pop("LLM_API_KEY_FILE", None)
                else:
                    os.environ["LLM_API_KEY_FILE"] = old_file
                if old_key is None:
                    os.environ.pop("LLM_API_KEY", None)
                else:
                    os.environ["LLM_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
