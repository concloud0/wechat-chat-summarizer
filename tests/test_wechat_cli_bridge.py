import hashlib
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wechat_cli_bridge as bridge


class WechatCliBridgeTests(unittest.TestCase):
    def test_missing_status_contains_setup_guidance(self):
        with mock.patch.object(bridge, "find_wechat_cli", return_value=None):
            status = bridge.get_status()

        self.assertFalse(status.available)
        self.assertIn("python -m pip install", status.message)
        self.assertIn("wechat-cli init", status.message)

    def test_parse_sessions_from_json(self):
        output = """
[
  {"name": "AI交流群", "display_name": "AI交流群", "last_time": "2026-06-03"},
  {"nickname": "张三", "userName": "wxid_123"},
  {"chat": "项目群", "username": "123@chatroom"}
]
"""

        sessions = bridge.parse_sessions_output(output)

        self.assertEqual([item.name for item in sessions], ["AI交流群", "张三", "项目群"])
        self.assertEqual(sessions[0].display_name, "AI交流群")

    def test_parse_sessions_from_text(self):
        output = """
1. AI交流群      2026-06-03
2. 项目群        2026-06-02
"""

        sessions = bridge.parse_sessions_output(output)

        self.assertEqual([item.name for item in sessions], ["AI交流群", "项目群"])

    def test_list_sessions_invokes_wechat_cli(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout='[{"name":"项目群"}]', stderr="")

        sessions = bridge.list_sessions(limit=5, executable="wechat-cli", runner=runner)

        self.assertEqual(sessions[0].name, "项目群")
        self.assertEqual(calls[0], ["wechat-cli", "sessions", "--limit", "5", "--format", "json"])

    def test_list_sessions_filters_service_accounts_and_sorts_by_message_count(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if args[1] == "sessions":
                return subprocess.CompletedProcess(
                    args,
                    0,
                    stdout="""
[
  {"chat":"公众号","username":"gh_123","timestamp": 300},
  {"chat":"认证号","username":"wxid_news","timestamp": 300, "verify_flag": 8},
  {"chat":"最近小群","username":"111@chatroom","timestamp": 300},
  {"chat":"老同学","username":"wxid_abc","timestamp": 200},
  {"chat":"品牌客服","username":"123@openim","timestamp": 150},
  {"chat":"服务号折叠","username":"brandsessionholder","timestamp": 100}
]
""",
                    stderr="",
                )
            if args[1] == "stats":
                totals = {"最近小群": 20, "老同学": 80}
                return subprocess.CompletedProcess(args, 0, stdout=f'{{"total": {totals[args[2]]}}}', stderr="")
            raise AssertionError(args)

        sessions = bridge.list_sessions(
            limit=10,
            executable="wechat-cli",
            runner=runner,
            exclude_service=True,
            include_counts=True,
        )

        self.assertEqual([item.name for item in sessions], ["老同学", "最近小群"])
        self.assertEqual([item.message_count for item in sessions], [80, 20])

    def test_export_chat_text_reads_output_file(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_text("2026-06-03 09:00:00 张三: 测试消息", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        text = bridge.export_chat_text(
            "项目群",
            limit=20,
            start_time="2026-06-01",
            end_time="2026-06-03",
            executable="wechat-cli",
            runner=runner,
        )

        self.assertIn("测试消息", text)
        self.assertEqual(calls[0][:3], ["wechat-cli", "export", "项目群"])
        self.assertIn("--limit", calls[0])
        self.assertIn("--start-time", calls[0])
        self.assertIn("--end-time", calls[0])

    def test_message_counts_from_cache_uses_md5_message_tables(self):
        username = "44995492670@chatroom"
        table_name = f"Msg_{hashlib.md5(username.encode()).hexdigest()}"

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp_dir:
            db_path = Path(tmp_dir) / "message_0.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(f"CREATE TABLE [{table_name}] (id INTEGER)")
                conn.executemany(f"INSERT INTO [{table_name}] (id) VALUES (?)", [(1,), (2,), (3,)])
                conn.commit()
            finally:
                conn.close()

            sessions = [
                bridge.WechatSession(
                    name="高消息群",
                    display_name="高消息群",
                    raw={"username": username},
                )
            ]
            with mock.patch.object(
                bridge,
                "wechat_cli_cache_metadata",
                return_value={"message/message_0.db": {"path": str(db_path)}},
            ):
                counts = bridge.message_counts_from_cache(sessions)

        self.assertEqual(counts, {username: 3})


if __name__ == "__main__":
    unittest.main()
