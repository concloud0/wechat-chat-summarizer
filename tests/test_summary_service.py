import json
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


def structured_response_json():
    return json.dumps(
        {
            "schema_version": 1,
            "overview": "已确认接口方案，并保留风险问题。",
            "events": [{"summary": "讨论接口方案", "evidence_ids": ["M000002"]}],
            "decisions": [
                {
                    "decision": "接口字段使用 version 和 status",
                    "status": "confirmed",
                    "evidence_ids": ["M000002"],
                }
            ],
            "action_items": [
                {
                    "task": "提交测试报告",
                    "owner": None,
                    "deadline": None,
                    "status": "待确认",
                    "evidence_ids": ["M000001"],
                }
            ],
            "open_questions": [
                {
                    "question": "是否仍有风险",
                    "status": "open",
                    "answer": None,
                    "evidence_ids": ["M000003"],
                }
            ],
            "conflicts": [],
            "participants": [
                {
                    "name": "张三",
                    "contribution": "提出待办和风险问题",
                    "evidence_ids": ["M000001", "M000003"],
                }
            ],
            "information_gaps": [
                {"description": "测试报告负责人未明确", "evidence_ids": ["M000001"]}
            ],
        },
        ensure_ascii=False,
    )


class SummaryServiceTests(unittest.TestCase):
    def test_summarize_text_markdown(self):
        response = service.summarize_text(service.SummaryRequest(text=CHAT_TEXT))

        self.assertEqual(response.engine, "local")
        self.assertEqual(response.download_name, "wechat_summary.md")
        self.assertEqual(response.message_count, 3)
        self.assertIn("## 聊天时间范围", response.report)
        self.assertEqual(set(response.rendered_reports), {"markdown", "txt", "json"})
        self.assertEqual(response.report, response.rendered_reports["markdown"])

    def test_summarize_text_json(self):
        response = service.summarize_text(
            service.SummaryRequest(text=CHAT_TEXT, output_format="json")
        )

        self.assertEqual(response.download_name, "wechat_summary.json")
        self.assertIn('"message_count": 3', response.report)
        self.assertEqual(response.report, response.rendered_reports["json"])

    def test_summarize_text_txt_removes_markdown_markup(self):
        response = service.summarize_text(
            service.SummaryRequest(text=CHAT_TEXT, output_format="txt")
        )

        self.assertEqual(response.download_name, "wechat_summary.txt")
        self.assertIn("聊天时间范围", response.report)
        self.assertNotIn("## ", response.report)

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
        with mock.patch.object(summarizer, "call_deepseek_json", return_value=structured_response_json()) as api:
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
        self.assertEqual(options.reasoning_effort, "high")
        self.assertTrue(prompt.startswith("<chat_log>"))
        self.assertEqual(response.model, summarizer.DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(response.thinking, "enabled")
        self.assertEqual(response.download_name, "wechat_summary.md")
        self.assertEqual(response.chunk_count, 1)
        self.assertEqual(response.ai_call_count, 1)
        self.assertIn("M000002", response.report)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(set(response.rendered_reports), {"markdown", "txt", "json"})

    def test_summarize_text_deepseek_supports_txt_and_json(self):
        with mock.patch.object(summarizer, "call_deepseek_json", return_value=structured_response_json()):
            txt_response = service.summarize_text(
                service.SummaryRequest(
                    text=CHAT_TEXT,
                    engine="deepseek",
                    output_format="txt",
                    deepseek_api_key="test-api-key",
                )
            )
            json_response = service.summarize_text(
                service.SummaryRequest(
                    text=CHAT_TEXT,
                    engine="deepseek",
                    output_format="json",
                    deepseek_api_key="test-api-key",
                )
            )

        self.assertEqual(txt_response.download_name, "wechat_summary.txt")
        self.assertIn("总体概览", txt_response.report)
        self.assertNotIn("##", txt_response.report)
        self.assertEqual(json_response.download_name, "wechat_summary.json")
        payload = json.loads(json_response.report)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["evidence"]["M000002"]["speaker"], "李四")

    def test_summarize_text_openai_uses_fixed_model_and_independent_options(self):
        with mock.patch.object(
            summarizer,
            "call_openai_json",
            return_value=structured_response_json(),
        ) as api:
            response = service.summarize_text(
                service.SummaryRequest(
                    text=CHAT_TEXT,
                    engine="openai",
                    openai_api_key="openai-test-key",
                    openai_reasoning_effort="xhigh",
                    deepseek_api_key="deepseek-unused",
                )
            )

        options, prompt = api.call_args.args
        self.assertEqual(options.model, summarizer.DEFAULT_OPENAI_MODEL)
        self.assertEqual(options.reasoning_effort, "xhigh")
        self.assertTrue(prompt.startswith("<chat_log>"))
        self.assertEqual(response.engine, "openai")
        self.assertEqual(response.model, "gpt-5.5")
        self.assertEqual(response.thinking, "enabled")
        self.assertEqual(response.reasoning_effort, "xhigh")
        self.assertEqual(response.ai_call_count, 1)

    def test_summarize_text_openai_does_not_fall_back_to_deepseek_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OpenAI API Key"):
                service.summarize_text(
                    service.SummaryRequest(
                        text=CHAT_TEXT,
                        engine="openai",
                        deepseek_api_key="deepseek-only",
                    )
                )

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
