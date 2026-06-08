import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wxchat_summarizer as summarizer


class ParserTests(unittest.TestCase):
    def test_parse_multiple_common_formats_and_multiline(self):
        text = """导出说明：这行不是消息
2026-06-01 09:12:03 张三: 今天把需求文档发我一下
这是同一条消息的第二行
[2026/06/01 10:20] 王五：会议改到明天上午十点，可以吗？
李四 2026年6月1日 11:00:00 我来确认，今晚前给结论
2026-06-01 12:00:00 | 赵六 | 接口字段采用 version 和 status
2026-06-01 13:00:00 系统: 撤回了一条消息
"""
        result = summarizer.parse_chat_with_stats(text)

        self.assertEqual(result.ignored_lines, 1)
        self.assertEqual(result.ignored_line_samples, ((1, "导出说明：这行不是消息"),))
        self.assertEqual(len(result.messages), 4)
        self.assertIn("第二行", result.messages[0].content)
        self.assertEqual(result.messages[2].speaker, "李四")
        self.assertEqual(result.messages[3].speaker, "赵六")

    def test_date_filter_and_speaker_filter(self):
        messages = summarizer.parse_chat(
            """2026-06-01 09:00:00 张三: 第一条
2026-06-02 09:00:00 李四: 第二条
2026-06-03 09:00:00 张三: 第三条
"""
        )

        filtered = summarizer.filter_messages(
            messages,
            summarizer.parse_date_filter("2026-06-02"),
            summarizer.parse_date_filter("2026-06-03", end_of_day=True),
            ["张三"],
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].content, "第三条")

    def test_ignored_line_samples_are_limited_and_truncated(self):
        ignored = "\n".join(f"说明 {index} " + "x" * 300 for index in range(25))
        result = summarizer.parse_chat_with_stats(
            ignored + "\n2026-06-01 09:00:00 张三: 有效消息\n"
        )

        self.assertEqual(result.ignored_lines, 25)
        self.assertEqual(len(result.ignored_line_samples), 20)
        self.assertLessEqual(len(result.ignored_line_samples[0][1]), 240)


class EncodingTests(unittest.TestCase):
    def test_read_text_auto_detects_gb18030(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp_dir:
            path = Path(tmp_dir) / "chat_gbk.txt"
            path.write_bytes("2026-06-01 09:00:00 张三: 需求文档".encode("gb18030"))

            result = summarizer.read_text(path, "auto")

        self.assertEqual(result.encoding, "gb18030")
        self.assertIn("需求文档", result.text)

    def test_read_text_auto_detects_utf16_le_without_bom(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp_dir:
            path = Path(tmp_dir) / "chat_utf16le.txt"
            path.write_bytes("2026-06-01 09:00:00 张三: 需求文档".encode("utf-16-le"))

            result = summarizer.read_text(path, "auto")

        self.assertEqual(result.encoding, "utf-16-le")
        self.assertIn("需求文档", result.text)


class ClassificationTests(unittest.TestCase):
    def test_commitment_is_not_decision(self):
        categories = summarizer.classify_message("我来确认，今晚前给结论")

        self.assertIn("action", categories)
        self.assertNotIn("decision", categories)

    def test_question_proposal_is_not_decision(self):
        categories = summarizer.classify_message("会议改到明天上午十点，可以吗？")

        self.assertIn("question", categories)
        self.assertNotIn("decision", categories)

    def test_strong_decision_is_detected(self):
        categories = summarizer.classify_message("字段方案确认用 version 和 status，暂时不加 type")

        self.assertIn("decision", categories)


class ReportTests(unittest.TestCase):
    def test_report_contains_overview_and_sections(self):
        messages = summarizer.parse_chat(
            """2026-06-01 09:00:00 张三: 请提交测试报告
2026-06-01 10:00:00 李四: 接口字段采用 version 和 status
2026-06-01 11:00:00 王五: 还有风险吗？
"""
        )

        report = summarizer.build_report(messages, 5)

        self.assertIn("## 聊天时间范围", report)
        self.assertIn("## 参与人物", report)
        self.assertIn("## 主要事件", report)
        self.assertIn("## 核心摘要", report)
        self.assertIn("## 原文依据", report)


class DeepSeekTests(unittest.TestCase):
    def test_deepseek_requires_api_key(self):
        messages = summarizer.parse_chat("2026-06-01 09:00:00 张三: 请提交测试报告\n")

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DeepSeek API Key"):
                summarizer.build_deepseek_report(messages, 5)

    def test_deepseek_report_uses_api_client(self):
        messages = summarizer.parse_chat("2026-06-01 09:00:00 张三: 请提交测试报告\n")

        with mock.patch.object(summarizer, "call_deepseek_chat", return_value="## 总览\n\n测试摘要\n") as api:
            report = summarizer.build_deepseek_report(messages, 5, api_key="test-api-key")

        self.assertIn("测试摘要", report)
        options, prompt = api.call_args.args
        self.assertEqual(options.model, summarizer.DEFAULT_DEEPSEEK_MODEL)
        self.assertTrue(prompt.startswith("原始聊天记录："))
        self.assertNotIn("生成时间", prompt)
        self.assertIn("聊天时间范围", prompt)
        self.assertIn("参与人物", prompt)
        self.assertIn("主要事件", prompt)
        self.assertIn("核心摘要", prompt)
        self.assertIn("原文依据", prompt)
        self.assertIn("请提交测试报告", prompt)

    def test_deepseek_thinking_payload(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"ok"}}]}'

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            captured["payload"] = request.data.decode("utf-8")
            return FakeResponse()

        options = summarizer.DeepSeekOptions(
            api_key="test-api-key",
            model="deepseek-v4-pro",
            thinking_enabled=True,
            reasoning_effort="medium",
        )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = summarizer.call_deepseek_chat(options, "测试")

        payload = summarizer.json.loads(captured["payload"])
        self.assertEqual(result, "ok\n")
        self.assertEqual(payload["model"], "deepseek-v4-pro")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertNotIn("temperature", payload)

    def test_connection_test_uses_minimal_non_thinking_request(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"OK"}}]}'

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            captured["payload"] = summarizer.json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = summarizer.test_deepseek_connection("test-api-key")

        self.assertEqual(result, "OK\n")
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(captured["payload"]["max_tokens"], 8)
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["payload"]["messages"][1]["content"], "仅回复 OK")


if __name__ == "__main__":
    unittest.main()
