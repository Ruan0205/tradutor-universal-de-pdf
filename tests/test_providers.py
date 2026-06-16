import json
import unittest

from translator.providers import MockProvider, OllamaProvider, TranslationRequest


class ProviderTests(unittest.TestCase):
    def test_mock_provider_is_deterministic(self):
        provider = MockProvider()
        result = provider.translate(TranslationRequest(block_id="b1", text="The spell deals damage."))

        self.assertEqual(result.block_id, "b1")
        self.assertEqual(result.provider, "mock")
        self.assertIn("The spell deals damage.", result.translated_text)
        self.assertEqual(result.confidence, 1.0)

    def test_ollama_provider_disables_reasoning_and_limits_output(self):
        provider = OllamaProvider(
            "http://localhost:11434",
            "qwen3.5:9b",
            reasoning_mode="off",
            max_output_tokens=128,
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
                            }
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


if __name__ == "__main__":
    unittest.main()
