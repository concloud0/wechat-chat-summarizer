#!/usr/bin/env python3
"""Local browser UI for the WeChat chat summarizer."""

from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import threading
import urllib.parse
import webbrowser
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import service
from . import wechat_cli_bridge
from .version import APP_VERSION


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def base_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def web_dir() -> Path:
    return base_dir() / "web"


def safe_print(message: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is None:
        return
    try:
        print(message, file=stream)
    except OSError:
        return


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, bytes]]:
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=policy.default).parsebytes(header + body)
    fields: dict[str, str] = {}
    files: dict[str, bytes] = {}

    if not message.is_multipart():
        return fields, files

    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        if disposition != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            files[name] = payload
            fields[f"{name}_filename"] = filename
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset, errors="replace")
    return fields, files


def parse_speakers(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def build_api_response(fields: dict[str, str], files: dict[str, bytes]) -> dict[str, object]:
    file_data = files.get("chat_file")
    if not file_data:
        raise ValueError("请选择聊天记录文件。")
    request = service.summary_request_from_fields(fields, source="file")
    return service.summarize_file(file_data, request).to_api_dict()


def build_report_response_from_text(chat_text: str, fields: dict[str, str], source: str) -> dict[str, object]:
    request = service.summary_request_from_fields(fields, source=source, text=chat_text, encoding="utf-8")
    return service.summarize_text(request).to_api_dict()


def json_request_body(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length > MAX_UPLOAD_BYTES:
        raise ValueError("请求过大。")
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("请求格式错误。")
    return {str(key): "" if value is None else str(value) for key, value in payload.items()}


def wechat_status_response() -> dict[str, object]:
    status = wechat_cli_bridge.get_status()
    return {
        "ok": True,
        "available": status.available,
        "executable": status.executable,
        "message": status.message,
        "install_command": "python -m pip install git+https://github.com/huohuoer/wechat-cli.git",
        "init_command": "wechat-cli init",
    }


def wechat_sessions_response(query: str) -> dict[str, object]:
    params = urllib.parse.parse_qs(query)
    limit = int(params.get("limit", ["50"])[0] or "50")
    sessions = wechat_cli_bridge.list_sessions(limit=limit, exclude_service=True, include_counts=True)
    return {
        "ok": True,
        "sessions": [
            {
                "name": session.name,
                "display_name": session.display_name,
                "message_count": session.message_count,
            }
            for session in sessions
        ],
    }


def wechat_summarize_response(fields: dict[str, str]) -> dict[str, object]:
    chat_name = fields.get("wechat_chat", "")
    limit = int(fields.get("wechat_limit") or "200")
    request = service.summary_request_from_fields(fields, source="wechat-cli", encoding="utf-8")
    return service.summarize_wechat(
        chat_name,
        limit=limit,
        start_time=fields.get("wechat_start_time") or fields.get("date_from") or None,
        end_time=fields.get("wechat_end_time") or fields.get("date_to") or None,
        request=request,
    ).to_api_dict()


class AppHandler(BaseHTTPRequestHandler):
    server_version = f"WeChatSummarizer/{APP_VERSION}"

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/wechat/status":
            self.write_json(wechat_status_response())
            return
        if parsed.path == "/api/wechat/sessions":
            try:
                self.write_json(wechat_sessions_response(parsed.query))
            except Exception as exc:
                self.write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        path = parsed.path
        if path == "/":
            path = "/index.html"
        target = (web_dir() / path.lstrip("/")).resolve()
        root = web_dir().resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/shutdown":
            self.write_json({"ok": True, "message": "程序正在关闭。"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if path == "/api/wechat/summarize":
            try:
                fields = json_request_body(self)
                self.write_json(wechat_summarize_response(fields))
            except Exception as exc:
                self.write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path != "/api/summarize":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_UPLOAD_BYTES:
                raise ValueError("文件过大，请选择 50MB 以内的文本文件。")
            body = self.rfile.read(length)
            fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
            response = build_api_response(fields, files)
            self.write_json(response)
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def write_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        safe_print(f"[web] {self.address_string()} - {format % args}")


def find_free_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex((host, preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local browser UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not web_dir().is_dir():
        safe_print(f"web assets not found: {web_dir()}", error=True)
        return 2

    port = find_free_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), AppHandler)
    url = f"http://{args.host}:{port}/"
    safe_print(f"微信聊天摘要工具已启动：{url}")
    safe_print("按 Ctrl+C 停止。")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
