"""Bridge helpers for the optional external `wechat-cli` command."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


Runner = Callable[..., subprocess.CompletedProcess[str]]
DEFAULT_TIMEOUT = 120
WECHAT_CLI_SETUP_GUIDANCE = (
    "未检测到 wechat-cli。\n\n"
    "微信会话直读是可选功能，需要额外安装 Python 和 wechat-cli：\n"
    "python -m pip install git+https://github.com/huohuoer/wechat-cli.git\n"
    "wechat-cli init\n\n"
    "初始化时请保持微信电脑版已登录。文本文件摘要不受影响。"
)


class WechatCliError(RuntimeError):
    """Raised when wechat-cli is unavailable or returns an error."""


@dataclass(frozen=True)
class WechatSession:
    name: str
    display_name: str
    raw: dict[str, Any]
    message_count: int | None = None


@dataclass(frozen=True)
class WechatCliStatus:
    available: bool
    executable: str | None
    message: str


def find_wechat_cli() -> str | None:
    explicit = os.environ.get("WECHAT_CLI")
    if explicit and Path(explicit).exists():
        return explicit

    found = shutil.which("wechat-cli")
    if found:
        return found

    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "anaconda3" / "Scripts" / "wechat-cli.exe",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Roaming" / "Python",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            matches = sorted(candidate.glob("**/wechat-cli.exe"))
            if matches:
                return str(matches[-1])
    return None


def get_status(executable: str | None = None, runner: Runner = subprocess.run) -> WechatCliStatus:
    resolved = executable or find_wechat_cli()
    if not resolved:
        return WechatCliStatus(
            available=False,
            executable=None,
            message=WECHAT_CLI_SETUP_GUIDANCE,
        )

    try:
        run_wechat_cli(["--help"], executable=resolved, runner=runner, timeout=15)
    except WechatCliError as exc:
        return WechatCliStatus(available=False, executable=resolved, message=str(exc))
    return WechatCliStatus(available=True, executable=resolved, message="wechat-cli 可用")


def run_wechat_cli(
    args: list[str],
    executable: str | None = None,
    runner: Runner = subprocess.run,
    timeout: int = DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    resolved = executable or find_wechat_cli()
    if not resolved:
        raise WechatCliError(WECHAT_CLI_SETUP_GUIDANCE)

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    try:
        result = runner(
            [resolved, *args],
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
            env=child_env,
        )
    except FileNotFoundError as exc:
        raise WechatCliError(WECHAT_CLI_SETUP_GUIDANCE) from exc
    except subprocess.TimeoutExpired as exc:
        raise WechatCliError("wechat-cli 执行超时，请确认微信已登录并且工具已初始化。") from exc

    result = normalize_completed_process(result)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WechatCliError(detail or f"wechat-cli 退出码：{result.returncode}")
    return result


def normalize_completed_process(result: subprocess.CompletedProcess[Any]) -> subprocess.CompletedProcess[str]:
    stdout = decode_output(result.stdout)
    stderr = decode_output(result.stderr)
    return subprocess.CompletedProcess(result.args, result.returncode, stdout=stdout, stderr=stderr)


def decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030", "utf-16"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace")
    return str(value)


def list_sessions(
    limit: int = 50,
    executable: str | None = None,
    runner: Runner = subprocess.run,
    exclude_service: bool = False,
    include_counts: bool = False,
) -> list[WechatSession]:
    safe_limit = max(1, min(int(limit), 500))
    fetch_limit = 500 if include_counts else safe_limit
    result = run_wechat_cli(
        ["sessions", "--limit", str(fetch_limit), "--format", "json"],
        executable=executable,
        runner=runner,
    )
    sessions = parse_sessions_output(result.stdout)
    if exclude_service:
        sessions = attach_contact_metadata(sessions)
        sessions = [session for session in sessions if not is_service_session(session)]
    if include_counts:
        ensure_message_cache(sessions, executable=executable, runner=runner)
        counts = message_counts_from_cache(sessions)
        sessions = enrich_session_counts(sessions, counts=counts, executable=executable, runner=runner)
        sessions = sorted(
            sessions,
            key=lambda session: (
                session.message_count if session.message_count is not None else -1,
                raw_timestamp(session.raw),
            ),
            reverse=True,
        )
    return sessions[:safe_limit]


def parse_sessions_output(output: str) -> list[WechatSession]:
    text = output.strip()
    if not text:
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return parse_text_sessions(text)

    if isinstance(payload, dict):
        for key in ("sessions", "data", "items", "result"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    if not isinstance(payload, list):
        return []

    sessions: list[WechatSession] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = first_string(item, ("chat", "name", "display_name", "nickname", "remark", "title", "chat_name", "userName", "username"))
        if not name:
            continue
        display = first_string(item, ("display_name", "nickname", "remark", "name", "title", "chat", "chat_name")) or name
        sessions.append(WechatSession(name=name, display_name=display, raw=item))
    return dedupe_sessions(sessions)


def parse_text_sessions(text: str) -> list[WechatSession]:
    sessions: list[WechatSession] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("---", "===", "Recent", "Name")):
            continue
        cleaned = re.sub(r"^\s*\d+[\).、-]\s*", "", line)
        cleaned = re.split(r"\s{2,}|\t", cleaned, maxsplit=1)[0].strip()
        if cleaned:
            sessions.append(WechatSession(name=cleaned, display_name=cleaned, raw={"line": raw_line}))
    return dedupe_sessions(sessions)


def dedupe_sessions(sessions: list[WechatSession]) -> list[WechatSession]:
    seen: set[str] = set()
    result: list[WechatSession] = []
    for session in sessions:
        if session.name in seen:
            continue
        seen.add(session.name)
        result.append(session)
    return result


def is_service_session(session: WechatSession) -> bool:
    username = str(session.raw.get("username") or session.raw.get("userName") or "").strip()
    name = session.name.strip()
    lowered = username.lower() or name.lower()
    if not lowered:
        return True
    if "@chatroom" in lowered:
        return False
    if lowered.endswith("@openim") or "@openim" in lowered:
        return True
    verify_flag = session.raw.get("verify_flag")
    if isinstance(verify_flag, int) and verify_flag > 0:
        return True
    if lowered.startswith("wxid_"):
        return False
    if re.fullmatch(r"\d{5,}", lowered):
        return False
    service_names = {
        "brandsessionholder",
        "brandservicesessionholder",
        "@placeholder_foldgroup",
        "weixin",
        "newsapp",
        "qqmail",
        "fmessage",
        "medianote",
        "floatbottle",
    }
    if lowered in service_names:
        return True
    if lowered.startswith("gh_"):
        return True
    if lowered.startswith("@"):
        return True
    return False


def attach_contact_metadata(sessions: list[WechatSession]) -> list[WechatSession]:
    usernames = [session_username(session) for session in sessions]
    usernames = [username for username in usernames if username]
    if not usernames:
        return sessions

    details = load_contact_metadata(usernames)
    if not details:
        return sessions

    result: list[WechatSession] = []
    for session in sessions:
        username = session_username(session)
        detail = details.get(username)
        raw = session.raw if not detail else {**session.raw, **detail}
        result.append(
            WechatSession(
                name=session.name,
                display_name=session.display_name,
                raw=raw,
                message_count=session.message_count,
            )
        )
    return result


def load_contact_metadata(usernames: list[str]) -> dict[str, dict[str, int]]:
    db_path = wechat_cli_contact_cache_path()
    if not db_path:
        return {}

    placeholders = ",".join("?" for _ in usernames)
    query = f"SELECT username, verify_flag, local_type FROM contact WHERE username IN ({placeholders})"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(query, usernames).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}

    metadata: dict[str, dict[str, int]] = {}
    for username, verify_flag, local_type in rows:
        metadata[str(username)] = {
            "verify_flag": int(verify_flag or 0),
            "local_type": int(local_type or 0),
        }
    return metadata


def wechat_cli_contact_cache_path() -> str | None:
    payload = wechat_cli_cache_metadata()
    info = payload.get("contact\\contact.db") or payload.get("contact/contact.db")
    if not isinstance(info, dict):
        return None
    path = info.get("path")
    if isinstance(path, str) and Path(path).is_file():
        return path
    return None


def wechat_cli_cache_metadata() -> dict[str, Any]:
    mtimes_path = Path(tempfile.gettempdir()) / "wechat_cli_cache" / "_mtimes.json"
    if not mtimes_path.is_file():
        return {}
    try:
        payload = json.loads(mtimes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def session_username(session: WechatSession) -> str:
    return str(session.raw.get("username") or session.raw.get("userName") or "").strip()


def enrich_session_counts(
    sessions: list[WechatSession],
    counts: dict[str, int] | None = None,
    executable: str | None = None,
    runner: Runner = subprocess.run,
) -> list[WechatSession]:
    enriched: list[WechatSession] = []
    for session in sessions:
        username = session_username(session)
        count = counts.get(username) if counts else None
        if count is None:
            count = get_message_count(session.name, executable=executable, runner=runner)
        enriched.append(
            WechatSession(
                name=session.name,
                display_name=session.display_name,
                raw=session.raw,
                message_count=count,
            )
        )
    return enriched


def ensure_message_cache(
    sessions: list[WechatSession],
    executable: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    if message_cache_paths() or not sessions:
        return
    get_message_count(sessions[0].name, executable=executable, runner=runner)


def message_counts_from_cache(sessions: list[WechatSession]) -> dict[str, int]:
    usernames = {session_username(session) for session in sessions}
    usernames.discard("")
    table_to_username = {
        f"Msg_{hashlib.md5(username.encode()).hexdigest()}": username
        for username in usernames
    }
    if not table_to_username:
        return {}

    counts = {username: 0 for username in usernames}
    for db_path in message_cache_paths():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                existing_tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                    ).fetchall()
                }
                for table_name, username in table_to_username.items():
                    if table_name not in existing_tables:
                        continue
                    row = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()
                    counts[username] += int(row[0] or 0)
            finally:
                conn.close()
        except sqlite3.Error:
            continue
    return {username: count for username, count in counts.items() if count > 0}


def message_cache_paths() -> list[str]:
    paths: list[str] = []
    for key, info in wechat_cli_cache_metadata().items():
        if not isinstance(info, dict):
            continue
        normalized = key.replace("/", "\\")
        if not re.fullmatch(r"message\\message_\d+\.db", normalized):
            continue
        path = info.get("path")
        if isinstance(path, str) and Path(path).is_file():
            paths.append(path)
    return paths


def get_message_count(
    chat_name: str,
    executable: str | None = None,
    runner: Runner = subprocess.run,
) -> int | None:
    try:
        result = run_wechat_cli(
            ["stats", chat_name, "--format", "json"],
            executable=executable,
            runner=runner,
            timeout=DEFAULT_TIMEOUT,
        )
        payload = json.loads(result.stdout)
    except (WechatCliError, json.JSONDecodeError, TypeError, ValueError):
        return None
    total = payload.get("total") if isinstance(payload, dict) else None
    return int(total) if isinstance(total, int) else None


def raw_timestamp(raw: dict[str, Any]) -> int:
    value = raw.get("timestamp") or raw.get("last_timestamp") or raw.get("last_time")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def export_chat_text(
    chat_name: str,
    limit: int,
    start_time: str | None = None,
    end_time: str | None = None,
    executable: str | None = None,
    runner: Runner = subprocess.run,
) -> str:
    if not chat_name.strip():
        raise WechatCliError("请选择要导出的微信会话。")
    safe_limit = max(1, min(int(limit), 20000))

    with tempfile.TemporaryDirectory(prefix="wechat_summary_") as temp_dir:
        output_path = Path(temp_dir) / "wechat_export.txt"
        args = ["export", chat_name, "--format", "txt", "--output", str(output_path), "--limit", str(safe_limit)]
        if start_time:
            args.extend(["--start-time", start_time])
        if end_time:
            args.extend(["--end-time", end_time])
        result = run_wechat_cli(args, executable=executable, runner=runner, timeout=DEFAULT_TIMEOUT)

        if output_path.exists():
            text = output_path.read_text(encoding="utf-8", errors="replace")
        else:
            text = result.stdout
    if not text.strip():
        raise WechatCliError("wechat-cli 没有导出任何聊天记录，请检查会话名称、时间范围和消息数量。")
    return text
