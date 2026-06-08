import json
import tempfile
import unittest
from pathlib import Path

from wxchat_app import settings


class FakeProtector:
    def protect(self, value):
        return f"protected:{value[::-1]}"

    def unprotect(self, value):
        if not value.startswith("protected:"):
            raise ValueError("invalid protected value")
        return value.removeprefix("protected:")[::-1]


class SettingsStoreTests(unittest.TestCase):
    def make_store(self, directory):
        return settings.SettingsStore(Path(directory) / "settings.json", FakeProtector())

    def test_round_trip_protects_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            values = settings.AppSettings(
                source="wechat",
                engine="deepseek",
                deepseek_api_key="test-api-key-secret",
                deepseek_effort="high",
                advanced_expanded=True,
                preview_mode="source",
            )
            store.save(values)

            raw = store.path.read_text(encoding="utf-8")
            restored = store.load()

        self.assertNotIn("test-api-key-secret", raw)
        self.assertEqual(restored.deepseek_api_key, "test-api-key-secret")
        self.assertEqual(restored.source, "wechat")
        self.assertEqual(restored.deepseek_effort, "high")
        self.assertTrue(restored.advanced_expanded)
        self.assertEqual(restored.preview_mode, "source")

    def test_clearing_api_key_removes_protected_value(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.save(settings.AppSettings(deepseek_api_key="test-api-key"))
            store.save(settings.AppSettings(deepseek_api_key=""))
            payload = json.loads(store.path.read_text(encoding="utf-8"))

        self.assertNotIn("deepseek_api_key_protected", payload)

    def test_invalid_values_fall_back_without_breaking_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.path.write_text(
                json.dumps(
                    {
                        "source": "invalid",
                        "engine": "deepseek",
                        "output_format": "json",
                        "encoding": "invalid",
                        "top_messages": -4,
                        "deepseek_api_key_protected": "broken",
                    }
                ),
                encoding="utf-8",
            )
            restored = store.load()

        self.assertEqual(restored.source, "file")
        self.assertEqual(restored.engine, "deepseek")
        self.assertEqual(restored.output_format, "markdown")
        self.assertEqual(restored.encoding, "auto")
        self.assertEqual(restored.top_messages, "8")
        self.assertEqual(restored.deepseek_api_key, "")

    def test_broken_json_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.path.write_text("{broken", encoding="utf-8")
            restored = store.load()

        self.assertEqual(restored.engine, "deepseek")
        self.assertEqual(restored.output_format, "markdown")
