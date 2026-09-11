"""Unit tests for configuration system."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from atlas_agent.config import (
    resolve_config,
    Config,
    save_file_config,
    load_file_config,
    prompt_api_key_if_missing
)
from atlas_agent.providers import create_provider

class TestConfig(unittest.TestCase):
    def test_masked_api_key(self):
        cfg = Config(api_key="AIzaSy1234567890abcdef")
        masked = cfg.masked_api_key()
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("cdef"))
        self.assertNotIn("1234567890", masked)

    def test_masked_empty_key(self):
        cfg = Config(api_key=None)
        self.assertEqual(cfg.masked_api_key(), "(not configured)")

    def test_cli_overrides_defaults(self):
        cfg = resolve_config({"model": "custom-model", "temperature": 0.7})
        self.assertEqual(cfg.model, "custom-model")
        self.assertEqual(cfg.temperature, 0.7)

    def test_save_and_load_file_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "config.json"
            cfg = Config(
                provider="openrouter",
                model="deepseek/deepseek-chat",
                api_key="sk-or-v1-testkey123",
                endpoint="https://openrouter.ai/api/v1"
            )
            saved = save_file_config(cfg, cfg_path)
            self.assertTrue(saved)
            self.assertTrue(cfg_path.is_file())

            loaded = load_file_config(cfg_path)
            self.assertEqual(loaded.get("provider"), "openrouter")
            self.assertEqual(loaded.get("model"), "deepseek/deepseek-chat")
            self.assertEqual(loaded.get("api_key"), "sk-or-v1-testkey123")

            # Check resolving using this file
            resolved = resolve_config(config_path=cfg_path)
            self.assertEqual(resolved.provider, "openrouter")
            self.assertEqual(resolved.api_key, "sk-or-v1-testkey123")

    def test_openrouter_env_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-456"}, clear=False):
            cfg = resolve_config()
            self.assertEqual(cfg.provider, "openrouter")
            self.assertEqual(cfg.api_key, "sk-or-test-456")
            self.assertEqual(cfg.endpoint, "https://openrouter.ai/api/v1")

    def test_create_openrouter_provider(self):
        cfg = Config(
            provider="openrouter",
            api_key="sk-or-test-xyz",
            model="google/gemini-2.5-flash"
        )
        provider = create_provider(cfg)
        self.assertEqual(provider.endpoint, "https://openrouter.ai/api/v1")
        self.assertEqual(provider.model, "google/gemini-2.5-flash")

    @patch("builtins.input", side_effect=["1", "AIzaSySecretGeminiKey", "n"])
    def test_prompt_api_key_gemini(self, mock_input):
        with patch("sys.stdin.isatty", return_value=True):
            cfg = Config(api_key=None)
            res = prompt_api_key_if_missing(cfg, interactive=True)
            self.assertEqual(res.provider, "gemini")
            self.assertEqual(res.api_key, "AIzaSySecretGeminiKey")

    @patch("builtins.input", side_effect=["2", "sk-or-v1-openrouter-secret", "n"])
    def test_prompt_api_key_openrouter(self, mock_input):
        with patch("sys.stdin.isatty", return_value=True):
            cfg = Config(api_key=None)
            res = prompt_api_key_if_missing(cfg, interactive=True)
            self.assertEqual(res.provider, "openrouter")
            self.assertEqual(res.api_key, "sk-or-v1-openrouter-secret")
            self.assertEqual(res.endpoint, "https://openrouter.ai/api/v1")

if __name__ == "__main__":
    unittest.main()
