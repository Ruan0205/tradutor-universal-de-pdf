import unittest

from translator.providers import MockProvider, TranslationRequest


class ProviderTests(unittest.TestCase):
    def test_mock_provider_is_deterministic(self):
        provider = MockProvider()
        result = provider.translate(TranslationRequest(block_id="b1", text="The spell deals damage."))

        self.assertEqual(result.block_id, "b1")
        self.assertEqual(result.provider, "mock")
        self.assertIn("The spell deals damage.", result.translated_text)
        self.assertEqual(result.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
