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
                openai_api_key="openai-api-key-secret",
                openai_effort="xhigh",
                advanced_expanded=True,
                preview_mode="source",
            )
            store.save(values)

            raw = store.path.read_text(encoding="utf-8")
            restored = store.load()

        self.assertNotIn("test-api-key-secret", raw)
        self.assertNotIn("openai-api-key-secret", raw)
        self.assertEqual(restored.deepseek_api_key, "test-api-key-secret")
        self.assertEqual(restored.source, "wechat")
        self.assertEqual(restored.deepseek_effort, "high")
        self.assertEqual(restored.openai_api_key, "openai-api-key-secret")
        self.assertEqual(restored.openai_effort, "xhigh")
        self.assertTrue(restored.advanced_expanded)
        self.assertEqual(restored.preview_mode, "source")

    def test_clearing_api_key_removes_protected_value(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.save(settings.AppSettings(deepseek_api_key="test-api-key"))
            store.save(settings.AppSettings(deepseek_api_key=""))
            payload = json.loads(store.path.read_text(encoding="utf-8"))

        self.assertNotIn("deepseek_api_key_protected", payload)

    def test_clearing_openai_api_key_does_not_affect_deepseek_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.save(
                settings.AppSettings(
                    deepseek_api_key="deepseek-key",
                    openai_api_key="openai-key",
                )
            )
            store.save(
                settings.AppSettings(
                    deepseek_api_key="deepseek-key",
                    openai_api_key="",
                )
            )
            payload = json.loads(store.path.read_text(encoding="utf-8"))

        self.assertIn("deepseek_api_key_protected", payload)
        self.assertNotIn("openai_api_key_protected", payload)

    def test_legacy_deepseek_efforts_are_migrated(self):
        expected = {
            "low": "high",
            "medium": "high",
            "xhigh": "max",
            "max": "max",
        }
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            for legacy, migrated in expected.items():
                store.path.write_text(
                    json.dumps({"deepseek_effort": legacy}),
                    encoding="utf-8",
                )
                self.assertEqual(store.load().deepseek_effort, migrated)

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
        self.assertEqual(restored.output_format, "json")
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

    def test_txt_output_format_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.save(settings.AppSettings(output_format="txt"))
            restored = store.load()

        self.assertEqual(restored.output_format, "txt")
