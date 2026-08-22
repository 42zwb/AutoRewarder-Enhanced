import os
import json
import tempfile
import unittest
from unittest.mock import patch

from src.config import account_dir
from src.security import atomic_write_json, is_safe_rewards_url, safe_log_text


class SecurityHelperTests(unittest.TestCase):
    def test_account_paths_reject_traversal(self):
        with self.assertRaises(ValueError):
            account_dir("../outside")
        with self.assertRaises(ValueError):
            account_dir("account\\nested")
        self.assertTrue(
            account_dir("account-1").endswith(os.path.join("accounts", "account-1"))
        )

    def test_urls_and_logs_fail_closed(self):
        self.assertTrue(is_safe_rewards_url("https://www.bing.com/search?q=test"))
        self.assertFalse(is_safe_rewards_url("http://www.bing.com/search?q=test"))
        self.assertFalse(is_safe_rewards_url("https://evilbing.com/search?q=test"))
        self.assertFalse(is_safe_rewards_url("https://user:pass@www.bing.com/"))
        self.assertIn("<redacted>", safe_log_text("Authorization: Bearer secret-token"))
        self.assertNotIn(
            "secret-token", safe_log_text("Authorization: Bearer secret-token")
        )
        self.assertNotIn("\n", safe_log_text("line1\nline2"))

    def test_atomic_json_write_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            atomic_write_json(path, {"ok": True}, indent=2)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), '{\n  "ok": true\n}')

    def test_legacy_llm_key_is_migrated_out_of_settings_json(self):
        from src.accounts.settings import GlobalSettingsManager

        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            key_path = os.path.join(tmp, "llm_api_key.bin")
            with open(settings_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {"llm_api_key": "legacy-key", "use_llm_queries": True}, handle
                )
            with patch(
                "src.accounts.settings.GLOBAL_SETTINGS_PATH", settings_path
            ), patch("src.accounts.settings.LLM_API_KEY_PATH", key_path):
                manager = GlobalSettingsManager()
                self.assertNotIn("llm_api_key", manager.get_settings())
                self.assertEqual(manager.get_llm_config()["llm_api_key"], "legacy-key")
            with open(settings_path, "r", encoding="utf-8") as handle:
                self.assertNotIn("llm_api_key", json.load(handle))

    def test_generic_settings_save_does_not_write_api_key_to_json(self):
        from src.accounts.settings import GlobalSettingsManager

        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            key_path = os.path.join(tmp, "llm_api_key.bin")
            with patch(
                "src.accounts.settings.GLOBAL_SETTINGS_PATH", settings_path
            ), patch("src.accounts.settings.LLM_API_KEY_PATH", key_path):
                manager = GlobalSettingsManager()
                manager.save_settings({"llm_api_key": "generic-save-key", "x": 1})
                with open(settings_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertNotIn("llm_api_key", saved)
                self.assertEqual(
                    manager.get_llm_config()["llm_api_key"], "generic-save-key"
                )


if __name__ == "__main__":
    unittest.main()
