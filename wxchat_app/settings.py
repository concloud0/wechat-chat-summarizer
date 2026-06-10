"""Persistent desktop settings with Windows DPAPI secret protection."""

from __future__ import annotations

import base64
import ctypes
import dataclasses
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Protocol

from ctypes import wintypes

from . import summarizer


APP_DIR_NAME = "WeChatChatSummarizer"
SETTINGS_FILE_NAME = "settings.json"
SETTINGS_VERSION = 2

VALID_SOURCES = {"file", "wechat"}
VALID_ENCODINGS = {"auto", "utf-8", "gb18030", "utf-16"}
VALID_FORMATS = {"markdown", "txt", "json"}
VALID_ENGINES = {"local", "deepseek", "openai"}
VALID_DEEPSEEK_EFFORTS = {"high", "max"}
VALID_OPENAI_EFFORTS = {"low", "medium", "high", "xhigh"}
VALID_PREVIEW_MODES = {"reading", "source"}


class SecretProtector(Protocol):
    def protect(self, value: str) -> str: ...

    def unprotect(self, value: str) -> str: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDpapiProtector:
    """Encrypt secrets for the current Windows user."""

    _flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    _entropy = b"WeChatChatSummarizer.settings.v1"

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows DPAPI is only available on Windows.")

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return blob, buffer

    def protect(self, value: str) -> str:
        encrypted = self._crypt(value.encode("utf-8"), decrypt=False)
        return base64.b64encode(encrypted).decode("ascii")

    def unprotect(self, value: str) -> str:
        encrypted = base64.b64decode(value.encode("ascii"), validate=True)
        return self._crypt(encrypted, decrypt=True).decode("utf-8")

    def _crypt(self, data: bytes, *, decrypt: bool) -> bytes:
        input_blob, input_buffer = self._blob(data)
        entropy_blob, entropy_buffer = self._blob(self._entropy)
        output_blob = _DataBlob()
        _ = input_buffer, entropy_buffer

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if decrypt:
            success = crypt32.CryptUnprotectData(
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                self._flags,
                ctypes.byref(output_blob),
            )
        else:
            success = crypt32.CryptProtectData(
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                self._flags,
                ctypes.byref(output_blob),
            )
        if not success:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)


@dataclasses.dataclass
class AppSettings:
    source: str = "file"
    date_from: str = ""
    date_to: str = ""
    speakers: str = ""
    encoding: str = "auto"
    top_messages: str = "8"
    engine: str = "deepseek"
    output_format: str = "markdown"
    deepseek_api_key: str = ""
    deepseek_base_url: str = summarizer.DEFAULT_DEEPSEEK_BASE_URL
    deepseek_thinking: bool = True
    deepseek_effort: str = "high"
    openai_api_key: str = ""
    openai_base_url: str = summarizer.DEFAULT_OPENAI_BASE_URL
    openai_effort: str = "medium"
    max_input_chars: str = "60000"
    wechat_limit: str = "300"
    wechat_session_limit: str = "50"
    advanced_expanded: bool = False
    preview_mode: str = "reading"


def default_settings_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_DIR_NAME / SETTINGS_FILE_NAME


class SettingsStore:
    def __init__(
        self,
        path: Path | None = None,
        protector: SecretProtector | None = None,
    ) -> None:
        self.path = path or default_settings_path()
        self.protector = protector or WindowsDpapiProtector()

    def load(self) -> AppSettings:
        defaults = AppSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return defaults
        if not isinstance(payload, dict):
            return defaults

        api_key = ""
        encrypted_key = payload.get("deepseek_api_key_protected")
        if isinstance(encrypted_key, str) and encrypted_key:
            try:
                api_key = self.protector.unprotect(encrypted_key)
            except (OSError, ValueError, UnicodeError):
                api_key = ""
        openai_api_key = ""
        encrypted_openai_key = payload.get("openai_api_key_protected")
        if isinstance(encrypted_openai_key, str) and encrypted_openai_key:
            try:
                openai_api_key = self.protector.unprotect(encrypted_openai_key)
            except (OSError, ValueError, UnicodeError):
                openai_api_key = ""

        source = _choice(payload.get("source"), VALID_SOURCES, defaults.source)
        engine = _choice(payload.get("engine"), VALID_ENGINES, defaults.engine)
        output_format = _choice(payload.get("output_format"), VALID_FORMATS, defaults.output_format)

        return AppSettings(
            source=source,
            date_from=_date(payload.get("date_from")),
            date_to=_date(payload.get("date_to")),
            speakers=_text(payload.get("speakers"), defaults.speakers, 500),
            encoding=_choice(payload.get("encoding"), VALID_ENCODINGS, defaults.encoding),
            top_messages=_integer_text(payload.get("top_messages"), defaults.top_messages, 1, 100),
            engine=engine,
            output_format=output_format,
            deepseek_api_key=api_key,
            deepseek_base_url=_url(payload.get("deepseek_base_url"), defaults.deepseek_base_url),
            deepseek_thinking=_boolean(payload.get("deepseek_thinking"), defaults.deepseek_thinking),
            deepseek_effort=_deepseek_effort(payload.get("deepseek_effort"), defaults.deepseek_effort),
            openai_api_key=openai_api_key,
            openai_base_url=_url(payload.get("openai_base_url"), defaults.openai_base_url),
            openai_effort=_choice(
                payload.get("openai_effort"),
                VALID_OPENAI_EFFORTS,
                defaults.openai_effort,
            ),
            max_input_chars=_integer_text(payload.get("max_input_chars"), defaults.max_input_chars, 1000, 1_000_000),
            wechat_limit=_integer_text(payload.get("wechat_limit"), defaults.wechat_limit, 1, 100_000),
            wechat_session_limit=_integer_text(payload.get("wechat_session_limit"), defaults.wechat_session_limit, 1, 500),
            advanced_expanded=_boolean(payload.get("advanced_expanded"), defaults.advanced_expanded),
            preview_mode=_choice(payload.get("preview_mode"), VALID_PREVIEW_MODES, defaults.preview_mode),
        )

    def save(self, settings: AppSettings) -> None:
        payload: dict[str, object] = {
            "version": SETTINGS_VERSION,
            "source": settings.source,
            "date_from": settings.date_from,
            "date_to": settings.date_to,
            "speakers": settings.speakers,
            "encoding": settings.encoding,
            "top_messages": settings.top_messages,
            "engine": settings.engine,
            "output_format": settings.output_format,
            "deepseek_base_url": settings.deepseek_base_url,
            "deepseek_thinking": settings.deepseek_thinking,
            "deepseek_effort": settings.deepseek_effort,
            "openai_base_url": settings.openai_base_url,
            "openai_effort": settings.openai_effort,
            "max_input_chars": settings.max_input_chars,
            "wechat_limit": settings.wechat_limit,
            "wechat_session_limit": settings.wechat_session_limit,
            "advanced_expanded": settings.advanced_expanded,
            "preview_mode": settings.preview_mode,
        }
        if settings.deepseek_api_key:
            payload["deepseek_api_key_protected"] = self.protector.protect(settings.deepseek_api_key)
        if settings.openai_api_key:
            payload["openai_api_key_protected"] = self.protector.protect(settings.openai_api_key)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _choice(value: object, choices: set[str], default: str) -> str:
    return value if isinstance(value, str) and value in choices else default


def _deepseek_effort(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    return summarizer.normalize_deepseek_reasoning_effort(value)


def _text(value: object, default: str, max_length: int) -> str:
    return value[:max_length] if isinstance(value, str) else default


def _boolean(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _date(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def _integer_text(value: object, default: str, minimum: int, maximum: int) -> str:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return default
    return str(number) if minimum <= number <= maximum else default


def _url(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    if candidate.startswith(("https://", "http://")) and len(candidate) <= 500:
        return candidate
    return default
