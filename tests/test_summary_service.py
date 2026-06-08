import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wxchat_app import service
from wxchat_app import summarizer


CHAT_TEXT = """2026-06-01 09:00:00 张三: 请提交测试报告
2026-06-02 10:00:00 李四: 接口字段采用 version 和 status
2026-06-03 11:00:00 张三: 还有风险吗？
"""


class SummaryServiceTests(unittest.TestCase):
    def test_summarize_text_markdown(self):
        response = service.summarize_text(service.SummaryRequest(text=CHAT_TEXT))

        self.assertEqual(response.engine, "local")
        self.assertEqual(response.download_name, "wechat_summary.md")
        self.assertEqual(response.message_count, 3)
        self.assertIn("## 聊天时间范围", response.report)

    def test_summarize_text_json(self):
        response = service.summarize_text(
            service.SummaryRequest(text=CHAT_TEXT, output_format="json")
        )

        self.assertEqual(response.download_name, "wechat_summary.json")
        self.assertIn('"message_count": 3', response.report)

    def test_summarize_text_filters_date_and_speaker(self):
        response = service.summarize_text(
            service.SummaryRequest(
                text=CHAT_TEXT,
                date_from="2026-06-03",
                date_to="2026-06-03",
                speakers=("张三",),
            )
        )

        self.assertEqual(response.message_count, 1)
        self.assertIn("还有风险吗", response.report)

    def test_summarize_text_empty_local(self):
        response = service.summarize_text(service.SummaryRequest(text="导出说明"))

        self.assertEqual(response.message_count, 0)
        self.assertIn("未解析到有效聊天消息", response.report)
        self.assertEqual(response.ignored_line_samples, ((1, "导出说明"),))
        self.assertNotIn("ignored_line_samples", response.to_api_dict())

    def test_summarize_text_deepseek_requires_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DeepSeek API Key"):
                service.summarize_text(
                    service.SummaryRequest(text=CHAT_TEXT, engine="deepseek")
                )

    def test_summarize_text_deepseek_uses_fixed_model(self):
        with mock.patch.object(summarizer, "call_deepseek_chat", return_value="## 核心摘要\n\n测试\n") as api:
            response = service.summarize_text(
                service.SummaryRequest(
                    text=CHAT_TEXT,
                    engine="deepseek",
                    deepseek_api_key="test-api-key",
                    deepseek_thinking=True,
                    deepseek_reasoning_effort="medium",
                )
            )

        options, prompt = api.call_args.args
        self.assertEqual(options.model, summarizer.DEFAULT_DEEPSEEK_MODEL)
        self.assertTrue(prompt.startswith("原始聊天记录："))
        self.assertEqual(response.model, summarizer.DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(response.thinking, "enabled")
        self.assertEqual(response.download_name, "wechat_summary.md")

    def test_summarize_file_reads_bytes_encoding(self):
        data = "2026-06-01 09:00:00 张三: 需求文档".encode("gb18030")
        response = service.summarize_file(data, service.SummaryRequest())

        self.assertEqual(response.encoding, "gb18030")
        self.assertEqual(response.message_count, 1)

    def test_summarize_wechat_exports_then_summarizes(self):
        with mock.patch(
            "wxchat_app.wechat_cli_bridge.export_chat_text",
            return_value=CHAT_TEXT,
        ) as export:
            response = service.summarize_wechat(
                "项目群",
                20,
                service.SummaryRequest(date_from="2026-06-01", date_to="2026-06-03"),
            )

        export.assert_called_once()
        self.assertEqual(response.source, "wechat-cli")
        self.assertEqual(response.wechat_chat, "项目群")
        self.assertEqual(response.wechat_exported_chars, len(CHAT_TEXT))


if __name__ == "__main__":
    unittest.main()
