import importlib
import json
import os
import tempfile
import unittest
from unittest import mock


class ConfigLoaderTests(unittest.TestCase):
    def test_load_api_config_copies_examples_into_frozen_macos_writable_dir(self):
        with tempfile.TemporaryDirectory() as writable_root, tempfile.TemporaryDirectory() as bundle_root:
            bundle_config_dir = os.path.join(bundle_root, "config")
            os.makedirs(bundle_config_dir, exist_ok=True)

            api_example = {
                "version": "1.0.0",
                "defaultModel": "demo-model",
                "modelId": "demo-model",
                "models": [
                    {
                        "id": "demo-model",
                        "name": "Demo Model",
                        "provider": "openai",
                        "model": "gpt-demo",
                        "apiUrl": "https://example.com/v1/chat/completions",
                        "temperature": 0.7,
                        "maxTokens": 512,
                        "enabled": True,
                    }
                ],
            }
            secrets_example = {"apiKey": "your-api-key-here"}

            with open(os.path.join(bundle_config_dir, "api.json.example"), "w", encoding="utf-8") as handle:
                json.dump(api_example, handle, ensure_ascii=False, indent=2)
            with open(os.path.join(bundle_config_dir, "secrets.json.example"), "w", encoding="utf-8") as handle:
                json.dump(secrets_example, handle, ensure_ascii=False, indent=2)

            with mock.patch("peko.core.runtime_paths.get_writable_root", return_value=writable_root), \
                 mock.patch("peko.core.runtime_paths.get_bundle_root", return_value=bundle_root), \
                 mock.patch("sys.frozen", True, create=True):
                module = importlib.import_module("peko.ai.config_loader")
                module = importlib.reload(module)
                module._cached_api_config = None

                data = module.load_api_config()

                self.assertEqual(data["modelId"], "demo-model")
                self.assertTrue(os.path.isfile(os.path.join(writable_root, "config", "api.json")))
                self.assertTrue(os.path.isfile(os.path.join(writable_root, "config", "secrets.json")))

                with open(os.path.join(writable_root, "config", "api.json"), "r", encoding="utf-8") as handle:
                    saved_api = json.load(handle)
                with open(os.path.join(writable_root, "config", "secrets.json"), "r", encoding="utf-8") as handle:
                    saved_secrets = json.load(handle)

                self.assertEqual(saved_api["modelId"], "demo-model")
                self.assertEqual(saved_secrets["apiKey"], "your-api-key-here")


if __name__ == "__main__":
    unittest.main()
