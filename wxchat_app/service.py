"""Shared application service layer for summary generation."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from . import summarizer
from . import wechat_cli_bridge


@dataclasses.dataclass(frozen=True)
class SummaryRequest:
    text: str = ""
    source: str = "file"
    encoding: str = "auto"
    output_format: str = "markdown"
    date_from: str | None = None
    date_to: str | None = None
    speakers: tuple[str, ...] = ()
    top_messages: int = 8
    engine: str = "local"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = summarizer.DEFAULT_DEEPSEEK_BASE_URL
    deepseek_thinking: bool = False
    deepseek_reasoning_effort: str = "medium"
    max_input_chars: int = 60000


@dataclasses.dataclass(frozen=True)
class SummaryResponse:
    report: str
    download_name: str
    encoding: str
    message_count: int
    speaker_count: int
    ignored_lines: int
    engine: str
    model: str
    thinking: str
    reasoning_effort: str
    source: str
    wechat_chat: str = ""
    wechat_exported_chars: int = 0
    ignored_line_samples: tuple[tuple[int, str], ...] = ()

    def to_api_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": True,
            "report": self.report,
            "encoding": self.encoding,
            "message_count": self.message_count,
            "speaker_count": self.speaker_count,
            "ignored_lines": self.ignored_lines,
            "engine": self.engine,
            "model": self.model,
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "source": self.source,
            "download_name": self.download_name,
        }
        if self.wechat_chat:
            payload["wechat_chat"] = self.wechat_chat
        if self.wechat_exported_chars:
            payload["wechat_exported_chars"] = self.wechat_exported_chars
        return payload


def parse_speakers(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.replace("，", ",").split(",") if item.strip())


def summary_request_from_fields(
    fields: dict[str, str],
    *,
    source: str = "file",
    text: str = "",
    encoding: str | None = None,
) -> SummaryRequest:
    return normalize_request(
        SummaryRequest(
            text=text,
            source=source,
            encoding=encoding or fields.get("encoding", "auto") or "auto",
            output_format=fields.get("format", "markdown") or "markdown",
            date_from=clean_optional(fields.get("date_from")),
            date_to=clean_optional(fields.get("date_to")),
            speakers=parse_speakers(fields.get("speakers", "")),
            top_messages=int(fields.get("top_messages") or "8"),
            engine=fields.get("engine", "local") or "local",
            deepseek_api_key=clean_optional(fields.get("deepseek_api_key")),
            deepseek_base_url=fields.get("deepseek_base_url") or summarizer.DEFAULT_DEEPSEEK_BASE_URL,
            deepseek_thinking=fields.get("deepseek_thinking", "disabled") == "enabled",
            deepseek_reasoning_effort=fields.get("deepseek_reasoning_effort") or "medium",
            max_input_chars=int(fields.get("max_input_chars") or "60000"),
        )
    )


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_request(request: SummaryRequest) -> SummaryRequest:
    output_format = request.output_format if request.output_format in {"markdown", "json"} else "markdown"
    engine = request.engine if request.engine in {"local", "deepseek"} else "local"
    top_messages = int(request.top_messages)
    if top_messages < 1:
        raise ValueError("每类摘录数量必须大于 0。")

    return dataclasses.replace(
        request,
        output_format=output_format,
        engine=engine,
        top_messages=top_messages,
        max_input_chars=int(request.max_input_chars),
        speakers=tuple(item.strip() for item in request.speakers if item.strip()),
        date_from=clean_optional(request.date_from),
        date_to=clean_optional(request.date_to),
        deepseek_base_url=request.deepseek_base_url or summarizer.DEFAULT_DEEPSEEK_BASE_URL,
        deepseek_reasoning_effort=request.deepseek_reasoning_effort or "medium",
    )


def summarize_file(path_or_bytes: str | Path | bytes, request: SummaryRequest) -> SummaryResponse:
    request = normalize_request(request)
    if isinstance(path_or_bytes, bytes):
        read_result = summarizer.read_text_bytes(path_or_bytes, request.encoding)
    else:
        read_result = summarizer.read_text(Path(path_or_bytes), request.encoding)

    return summarize_text(
        dataclasses.replace(
            request,
            text=read_result.text,
            encoding=read_result.encoding,
        )
    )


def summarize_wechat(
    chat_name: str,
    limit: int,
    request: SummaryRequest,
    *,
    start_time: str | None = None,
    end_time: str | None = None,
) -> SummaryResponse:
    request = normalize_request(request)
    exported_text = wechat_cli_bridge.export_chat_text(
        chat_name=chat_name,
        limit=limit,
        start_time=start_time or request.date_from,
        end_time=end_time or request.date_to,
    )
    response = summarize_text(
        dataclasses.replace(
            request,
            text=exported_text,
            source="wechat-cli",
            encoding="utf-8",
        )
    )
    return dataclasses.replace(
        response,
        wechat_chat=chat_name,
        wechat_exported_chars=len(exported_text),
    )


def summarize_text(request: SummaryRequest) -> SummaryResponse:
    request = normalize_request(request)
    parse_result = summarizer.parse_chat_with_stats(request.text)
    date_from = summarizer.parse_date_filter(request.date_from)
    date_to = summarizer.parse_date_filter(request.date_to, end_of_day=True)
    messages = summarizer.filter_messages(parse_result.messages, date_from, date_to, list(request.speakers))

    report, extension = build_report(messages, parse_result, request)
    analysis = summarizer.analyze_messages(messages)
    thinking = "enabled" if request.deepseek_thinking and request.engine == "deepseek" else "disabled"
    reasoning_effort = request.deepseek_reasoning_effort if thinking == "enabled" else ""

    return SummaryResponse(
        report=report,
        download_name=f"wechat_summary.{extension}",
        encoding=request.encoding,
        message_count=len(messages),
        speaker_count=len(analysis.by_speaker),
        ignored_lines=parse_result.ignored_lines,
        engine=request.engine,
        model=summarizer.DEFAULT_DEEPSEEK_MODEL if request.engine == "deepseek" else "local",
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        source=request.source,
        ignored_line_samples=parse_result.ignored_line_samples,
    )


def build_report(
    messages: list[summarizer.Message],
    parse_result: summarizer.ParseResult,
    request: SummaryRequest,
) -> tuple[str, str]:
    if request.engine == "deepseek":
        return (
            summarizer.build_deepseek_report(
                messages,
                request.top_messages,
                api_key=request.deepseek_api_key,
                model=summarizer.DEFAULT_DEEPSEEK_MODEL,
                base_url=request.deepseek_base_url,
                thinking_enabled=request.deepseek_thinking,
                reasoning_effort=request.deepseek_reasoning_effort,
                max_input_chars=request.max_input_chars,
                parse_result=parse_result,
            ),
            "md",
        )
    if request.output_format == "json":
        return summarizer.build_json_report(messages, parse_result), "json"
    return summarizer.build_report(messages, request.top_messages, parse_result), "md"


def api_dict(response: SummaryResponse) -> dict[str, Any]:
    return response.to_api_dict()
