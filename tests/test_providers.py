import json
import unittest

from translator.providers import MockProvider, OllamaProvider, TranslationRequest


class ProviderTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
