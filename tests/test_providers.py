import json
import io
import tempfile
import unittest

from PIL import Image

from translator.providers import GoogleTranslateImagesProvider, MockProvider, OllamaProvider, OpenAICompatibleProvider, TranslationRequest


class FakeGoogleTranslateImagesProvider(GoogleTranslateImagesProvider):
    def _translate_with_browser(self, image_bytes: bytes, source_lang: str, target_lang: str) -> bytes:
        image = Image.new("RGB", (32, 16), color=(10, 120, 200))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class ProviderTests(unittest.TestCase):
    def test_google_translate_images_disabled_does_not_open_browser(self):
        provider = GoogleTranslateImagesProvider(enabled=False)
        result = provider.translate_image_bytes(b"not-an-image")

        self.assertIsNone(result)

    def test_google_translate_images_caches_browser_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeGoogleTranslateImagesProvider(cache_dir=tmp)
            first = provider.translate_image_bytes(b"input-image", source_lang="English", target_lang="Português Brasileiro")
            second = provider.translate_image_bytes(b"input-image", source_lang="en", target_lang="pt")

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertFalse(first.from_cache)
            self.assertTrue(second.from_cache)
            self.assertEqual(first.image_bytes, second.image_bytes)
            self.assertEqual(first.provider, "google_translate_images")
            self.assertEqual(second.source_lang, "en")
            self.assertEqual(second.target_lang, "pt")

    def test_mock_provider_is_deterministic(self):
        provider = MockProvider()
        result = provider.translate(TranslationRequest(block_id="b1", text="The spell deals damage."))

        self.assertEqual(result.block_id, "b1")
        self.assertEqual(result.provider, "mock")
        self.assertIn("portugues brasileiro", result.translated_text)
        self.assertNotIn("The spell deals damage.", result.translated_text)
        self.assertEqual(result.confidence, 1.0)

    def test_ollama_provider_disables_reasoning_and_limits_output(self):
        provider = OllamaProvider(
            "http://localhost:11434",
            "qwen3.5:9b",
            reasoning_mode="off",
            max_output_tokens=128,
            context_tokens=32768,
            num_gpu=0,
            num_thread=4,
            keep_alive="24h",
        )
        seen = {}

        def fake_urlopen(request, timeout):
            seen["timeout"] = timeout
            seen["payload"] = json.loads(request.data.decode("utf-8"))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "block_id": "b1",
                                        "translated_text": "O mago lanca um feitico.",
                                        "warnings": [],
                                        "confidence": 0.9,
                                    }
                                )
                            },
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                            "eval_duration": 2_000_000_000,
                            "total_duration": 3_000_000_000,
                        }
                    ).encode("utf-8")

            return Response()

        import translator.providers.inference as inference

        original = inference.urllib.request.urlopen
        try:
            inference.urllib.request.urlopen = fake_urlopen
            result = provider.translate(TranslationRequest(block_id="b1", text="The wizard casts a spell."))
        finally:
            inference.urllib.request.urlopen = original

        self.assertEqual(result.translated_text, "O mago lanca um feitico.")
        self.assertIs(seen["payload"]["think"], False)
        self.assertEqual(seen["payload"]["options"]["num_predict"], 128)
        self.assertEqual(seen["payload"]["options"]["num_ctx"], 32768)
        self.assertEqual(seen["payload"]["options"]["num_gpu"], 0)
        self.assertEqual(seen["payload"]["options"]["num_thread"], 4)
        self.assertEqual(seen["payload"]["keep_alive"], "24h")
        self.assertEqual(result.prompt_tokens, 12)
        self.assertEqual(result.completion_tokens, 8)
        self.assertEqual(result.total_tokens, 20)
        self.assertEqual(result.tokens_per_second, 4.0)

    def test_ollama_provider_rejects_missing_translated_text(self):
        provider = OllamaProvider("http://localhost:11434", "qwen3.5:9b")

        def fake_urlopen(request, timeout):
            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps({"message": {"content": json.dumps({"block_id": "b1"})}}).encode("utf-8")

            return Response()

        import translator.providers.inference as inference

        original = inference.urllib.request.urlopen
        try:
            inference.urllib.request.urlopen = fake_urlopen
            with self.assertRaises(RuntimeError):
                provider.translate(TranslationRequest(block_id="b1", text="The wizard casts a spell."))
        finally:
            inference.urllib.request.urlopen = original

    def test_ollama_provider_accepts_common_translation_key(self):
        provider = OllamaProvider("http://localhost:11434", "qwen3.5:9b")

        def fake_urlopen(request, timeout):
            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps({"message": {"content": json.dumps({"translation": "O dragao ataca."})}}).encode("utf-8")

            return Response()

        import translator.providers.inference as inference

        original = inference.urllib.request.urlopen
        try:
            inference.urllib.request.urlopen = fake_urlopen
            result = provider.translate(TranslationRequest(block_id="b1", text="The dragon attacks."))
        finally:
            inference.urllib.request.urlopen = original

        self.assertEqual(result.translated_text, "O dragao ataca.")

    def test_openai_compatible_provider_uses_bearer_key_and_existing_v1_url(self):
        provider = OpenAICompatibleProvider(
            "http://router:3005/llm/v1",
            "minimax-m3",
            api_key="proxy-key",
            temperature=0.1,
            max_output_tokens=4096,
        )
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["authorization"] = request.headers.get("Authorization")
            seen["payload"] = json.loads(request.data.decode("utf-8"))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {
                            "choices": [{"message": {"content": "O dragao ataca."}}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                        }
                    ).encode("utf-8")

            return Response()

        import translator.providers.inference as inference

        original = inference.urllib.request.urlopen
        try:
            inference.urllib.request.urlopen = fake_urlopen
            result = provider.translate(TranslationRequest(block_id="b1", text="The dragon attacks."))
        finally:
            inference.urllib.request.urlopen = original

        self.assertEqual(seen["url"], "http://router:3005/llm/v1/chat/completions")
        self.assertEqual(seen["authorization"], "Bearer proxy-key")
        self.assertEqual(seen["payload"]["model"], "minimax-m3")
        self.assertEqual(seen["payload"]["temperature"], 0.1)
        self.assertEqual(seen["payload"]["max_tokens"], 4096)
        self.assertEqual(result.translated_text, "O dragao ataca.")
        self.assertEqual(result.total_tokens, 15)


if __name__ == "__main__":
    unittest.main()
