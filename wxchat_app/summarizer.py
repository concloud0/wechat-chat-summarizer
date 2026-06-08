#!/usr/bin/env python3
"""Summarize exported WeChat chat text into a Markdown report."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_CHAT_PATH = "/chat/completions"
SPEAKER_MAX_CHARS = 120
TIME_RE = r"\d{4}(?:[-/]\d{1,2}[-/]\d{1,2}|年\d{1,2}月\d{1,2}日)[ T]?\d{1,2}:\d{2}(?::\d{2})?"
MESSAGE_PATTERNS = [
    re.compile(
        rf"^\[?(?P<time>{TIME_RE})\]?\s*(?:\t|\s+)"
        rf"(?P<speaker>[^:：\t|]{{1,{SPEAKER_MAX_CHARS}}})[:：]\s*(?P<content>.*)$"
    ),
    re.compile(
        rf"^\[?(?P<time>{TIME_RE})\]?\s*(?:\t|\s+)\|?\s*"
        rf"(?P<speaker>[^|\t]{{1,{SPEAKER_MAX_CHARS}}})\s*(?:\||\t)\s*(?P<content>.+)$"
    ),
    re.compile(
        rf"^(?P<speaker>[^:：\t|]{{1,{SPEAKER_MAX_CHARS}}})\s+(?P<time>{TIME_RE})[:：]?\s*(?P<content>.*)$"
    ),
    re.compile(
        rf"^\[?(?P<time>{TIME_RE})\]?\s+(?P<speaker>\S{{1,{SPEAKER_MAX_CHARS}}})\s+(?P<content>.+)$"
    ),
]
MESSAGE_START_RE = re.compile(rf"^\[?{TIME_RE}\]?")

AUTO_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "utf-16", "utf-16-le")
STOPWORDS = {
    "一个",
    "一下",
    "不是",
    "不能",
    "今天",
    "他们",
    "什么",
    "可以",
    "因为",
    "如果",
    "就是",
    "已经",
    "我们",
    "所以",
    "这个",
    "那个",
    "需要",
    "没有",
    "然后",
    "现在",
    "明天",
    "确认",
    "问题",
    "好的",
    "下午",
    "上午",
    "今晚",
    "暂时",
}

ACTION_HINTS = ("需要", "帮我", "记得", "麻烦", "请", "提交", "整理", "发送", "发我", "安排", "截止", "处理", "跟进")
COMMITMENT_HINTS = ("我来", "我会", "我负责", "稍后", "今晚前", "明天前", "下午", "给结论", "给反馈", "处理完")
QUESTION_HINTS = ("?", "？", "吗", "么", "谁", "如何", "怎么", "能否", "可不可以", "有没有")
DECISION_HINTS = ("决定", "结论是", "最终", "统一", "就用", "改为", "不加", "不用", "采用", "定为", "确认用", "已确认")
RISK_HINTS = ("风险", "阻塞", "延期", "来不及", "不确定", "报错", "失败", "不能", "缺少", "没法")
SYSTEM_HINTS = ("撤回了一条消息", "加入群聊", "退出群聊", "拍了拍", "以下为新消息", "已开启群聊")
KEYWORD_SUFFIXES = (
    "需求",
    "文档",
    "会议",
    "接口",
    "字段",
    "方案",
    "报告",
    "测试",
    "结论",
    "项目",
    "任务",
    "时间",
    "版本",
    "问题",
    "风险",
    "进度",
)
KNOWN_COMPOUNDS = (
    "需求文档",
    "接口字段",
    "字段方案",
    "测试报告",
    "项目进度",
    "会议时间",
    "风险问题",
    "版本方案",
)
TRIM_PREFIX_RE = re.compile(r"^(今天|明天|昨天|今晚|上午|下午|晚上|需要|确认|提交|整理|发送|帮我|麻烦|请|把)+")


@dataclasses.dataclass(frozen=True)
class Message:
    timestamp: dt.datetime
    speaker: str
    content: str
    line_no: int


@dataclasses.dataclass(frozen=True)
class ParseResult:
    messages: list[Message]
    ignored_lines: int
    ignored_line_samples: tuple[tuple[int, str], ...] = ()


@dataclasses.dataclass(frozen=True)
class ReadResult:
    text: str
    encoding: str


@dataclasses.dataclass(frozen=True)
class Analysis:
    messages: list[Message]
    term_counts: collections.Counter[str]
    by_day: dict[dt.date, list[Message]]
    by_speaker: collections.Counter[str]
    categories: dict[str, list[Message]]


@dataclasses.dataclass(frozen=True)
class DeepSeekOptions:
    api_key: str
    model: str = DEFAULT_DEEPSEEK_MODEL
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    thinking_enabled: bool = False
    reasoning_effort: str = "medium"
    max_input_chars: int = 60000
    timeout: int = 90


def parse_timestamp(value: str) -> dt.datetime:
    normalized = value.strip().replace("/", "-").replace("T", " ")
    normalized = normalized.replace("年", "-").replace("月", "-").replace("日", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    for fmt in formats:
        try:
            return dt.datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise ValueError(f"unsupported timestamp: {value}")


def parse_chat(text: str) -> list[Message]:
    return parse_chat_with_stats(text).messages


def parse_chat_with_stats(text: str) -> ParseResult:
    messages: list[Message] = []
    current: Message | None = None
    ignored_lines = 0
    ignored_line_samples: list[tuple[int, str]] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip("\ufeff").rstrip()
        if not line.strip():
            continue

        parsed = parse_message_line(line)
        if parsed:
            if current is not None:
                messages.append(current)
            timestamp, speaker, content = parsed
            current = Message(timestamp=timestamp, speaker=speaker, content=content, line_no=line_no)
        elif looks_like_message_start(line):
            ignored_lines += 1
            if len(ignored_line_samples) < 20:
                ignored_line_samples.append((line_no, line.strip()[:240]))
        elif current is not None:
            current = dataclasses.replace(current, content=f"{current.content}\n{line.strip()}")
        else:
            ignored_lines += 1
            if len(ignored_line_samples) < 20:
                ignored_line_samples.append((line_no, line.strip()[:240]))

    if current is not None:
        messages.append(current)

    filtered = [msg for msg in messages if not is_system_message(msg.content)]
    return ParseResult(
        messages=filtered,
        ignored_lines=ignored_lines,
        ignored_line_samples=tuple(ignored_line_samples),
    )


def parse_message_line(line: str) -> tuple[dt.datetime, str, str] | None:
    for pattern in MESSAGE_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        try:
            timestamp = parse_timestamp(match.group("time"))
        except ValueError:
            return None
        speaker = clean_speaker(match.group("speaker"))
        content = match.group("content").strip()
        if speaker and content:
            return timestamp, speaker, content
    return None


def looks_like_message_start(line: str) -> bool:
    return bool(MESSAGE_START_RE.match(line.strip()))


def clean_speaker(speaker: str) -> str:
    return speaker.strip().strip("|").strip()


def is_system_message(content: str) -> bool:
    return any(hint in content for hint in SYSTEM_HINTS)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}|[\u4e00-\u9fff]+", text):
        if word.lower() in STOPWORDS or word in STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            tokens.extend(extract_chinese_terms(word))
        else:
            tokens.append(word.lower())
    return tokens


def extract_chinese_terms(segment: str) -> list[str]:
    terms: list[str] = []
    for compound in KNOWN_COMPOUNDS:
        if compound in segment:
            terms.append(compound)
    for suffix in KEYWORD_SUFFIXES:
        for match in re.finditer(rf"[\u4e00-\u9fff]{{0,2}}{suffix}", segment):
            term = trim_chinese_term(match.group(0))
            if len(term) >= 2 and term not in STOPWORDS:
                terms.append(term)
    return dedupe_terms(terms)


def trim_chinese_term(term: str) -> str:
    term = TRIM_PREFIX_RE.sub("", term)
    term = re.sub(r"^[\u4e00-\u9fff]?把", "", term)
    return term.strip("我你他她它的了吧啊呢吗和与把被在到就都也很更再还先后前给来去")


def dedupe_terms(terms: list[str]) -> list[str]:
    unique = list(dict.fromkeys(term for term in terms if term))
    result: list[str] = []
    for term in unique:
        if any(term != other and term in other for other in unique):
            continue
        result.append(term)
    return result


def classify_message(content: str) -> set[str]:
    categories: set[str] = set()
    if is_question(content):
        categories.add("question")
    if is_decision(content):
        categories.add("decision")
    if is_action(content) or is_commitment(content):
        categories.add("action")
    if any(hint in content for hint in RISK_HINTS):
        categories.add("risk")
    return categories


def is_question(content: str) -> bool:
    return any(hint in content for hint in QUESTION_HINTS)


def is_decision(content: str) -> bool:
    if "给结论" in content or "等结论" in content:
        return False
    if is_question(content) and not any(hint in content for hint in ("决定", "结论是", "最终", "确认用")):
        return False
    return any(hint in content for hint in DECISION_HINTS)


def is_action(content: str) -> bool:
    return any(hint in content for hint in ACTION_HINTS)


def is_commitment(content: str) -> bool:
    return any(hint in content for hint in COMMITMENT_HINTS)


def analyze_messages(messages: list[Message]) -> Analysis:
    sorted_messages = sorted(messages, key=lambda msg: msg.timestamp)
    term_counts = collections.Counter(token for msg in sorted_messages for token in tokenize(msg.content))
    by_day: dict[dt.date, list[Message]] = collections.defaultdict(list)
    by_speaker = collections.Counter(msg.speaker for msg in sorted_messages)
    categories: dict[str, list[Message]] = collections.defaultdict(list)

    for msg in sorted_messages:
        by_day[msg.timestamp.date()].append(msg)
        for category in classify_message(msg.content):
            categories[category].append(msg)

    return Analysis(
        messages=sorted_messages,
        term_counts=term_counts,
        by_day=dict(by_day),
        by_speaker=by_speaker,
        categories=dict(categories),
    )


def score_message(message: Message, analysis: Analysis) -> int:
    tokens = tokenize(message.content)
    score = sum(analysis.term_counts[token] for token in tokens)
    categories = classify_message(message.content)
    score += 4 * len(categories)
    score += min(len(message.content) // 20, 3)
    return score


def pick_messages(messages: list[Message], analysis: Analysis, limit: int) -> list[Message]:
    candidates = sorted(messages, key=lambda msg: (score_message(msg, analysis), msg.timestamp), reverse=True)
    return sorted(candidates[:limit], key=lambda msg: msg.timestamp)


def format_message(msg: Message) -> str:
    time_text = msg.timestamp.strftime("%Y-%m-%d %H:%M")
    content = msg.content.replace("\n", " / ")
    return f"- `{time_text}` **{msg.speaker}**: {content}"


def build_overview(analysis: Analysis) -> list[str]:
    messages = analysis.messages
    top_terms = [term for term, _ in analysis.term_counts.most_common(4)]
    active = analysis.by_speaker.most_common(3)
    days = len(analysis.by_day)
    topic_text = "、".join(top_terms) if top_terms else "未提取到明显主题"
    active_text = "、".join(f"{name}({count}条)" for name, count in active) if active else "无"
    action_count = len(analysis.categories.get("action", []))
    question_count = len(analysis.categories.get("question", []))
    decision_count = len(analysis.categories.get("decision", []))
    risk_count = len(analysis.categories.get("risk", []))

    return [
        f"- 本次聊天覆盖 {days} 天，共 {len(messages)} 条消息，主要围绕：{topic_text}。",
        f"- 活跃成员：{active_text}。",
        f"- 识别到 {action_count} 条待办/跟进、{question_count} 条问题、{decision_count} 条决定/结论、{risk_count} 条风险提示。",
    ]


def build_main_events(analysis: Analysis, limit: int) -> list[str]:
    events: list[str] = []
    if analysis.term_counts:
        terms = "、".join(term for term, _ in analysis.term_counts.most_common(6))
        events.append(f"- 主要围绕：{terms}。")
    for title, category in (
        ("决定", "decision"),
        ("待办", "action"),
        ("问题", "question"),
        ("风险", "risk"),
    ):
        picked = pick_messages(analysis.categories.get(category, []), analysis, max(1, min(3, limit)))
        if picked:
            summary = "；".join(f"{msg.speaker}: {msg.content.replace(chr(10), ' / ')}" for msg in picked)
            events.append(f"- {title}：{summary}")
    return events or ["- 未识别到明显事件。"]


def build_participants(analysis: Analysis) -> list[str]:
    return [f"- {speaker}: {count} 条" for speaker, count in analysis.by_speaker.most_common(10)] or ["- 未明确"]


def build_report(messages: list[Message], top_messages: int, parse_result: ParseResult | None = None) -> str:
    if not messages:
        return "# 微信聊天记录摘要\n\n未解析到有效聊天消息。请检查输入格式或文件编码。\n"

    analysis = analyze_messages(messages)
    start = analysis.messages[0].timestamp.strftime("%Y-%m-%d %H:%M")
    end = analysis.messages[-1].timestamp.strftime("%Y-%m-%d %H:%M")
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    key_messages = pick_messages(analysis.messages, analysis, top_messages)

    lines = [
        "# 微信聊天记录摘要",
        "",
        f"- 生成时间：{generated_at}",
        f"- 消息数量：{len(analysis.messages)}",
    ]
    if parse_result and parse_result.ignored_lines:
        lines.append(f"- 未识别开头行：{parse_result.ignored_lines} 行")

    lines.extend(["", "## 聊天时间范围", ""])
    lines.append(f"- {start} 至 {end}")

    lines.extend(["", "## 参与人物", ""])
    lines.extend(build_participants(analysis))

    lines.extend(["", "## 主要事件", ""])
    lines.extend(build_main_events(analysis, top_messages))

    lines.extend(["", "## 核心摘要", ""])
    lines.extend(build_overview(analysis))

    lines.extend(["", "## 原文依据", ""])
    if key_messages:
        lines.extend(format_message(msg) for msg in key_messages)
    else:
        lines.append("未识别到相关消息。")

    lines.append("")
    return "\n".join(lines)


def build_model_context(messages: list[Message], top_messages: int) -> str:
    if not messages:
        return "未解析到有效聊天消息。"

    analysis = analyze_messages(messages)
    key_messages = pick_messages(analysis.messages, analysis, top_messages)
    lines = [
        "辅助统计：",
        f"- 消息数量：{len(analysis.messages)}",
        f"- 参与人数：{len(analysis.by_speaker)}",
        "",
        "参与人物统计：",
        *build_participants(analysis),
        "",
        "主要事件线索：",
        *build_main_events(analysis, top_messages),
        "",
        "关键原文线索：",
    ]
    if key_messages:
        lines.extend(format_message(msg) for msg in key_messages)
    else:
        lines.append("- 未识别到相关消息。")
    return "\n".join(lines)


def build_json_report(messages: list[Message], parse_result: ParseResult | None = None) -> str:
    analysis = analyze_messages(messages)
    payload = {
        "message_count": len(analysis.messages),
        "speaker_count": len(analysis.by_speaker),
        "ignored_lines": parse_result.ignored_lines if parse_result else 0,
        "top_terms": analysis.term_counts.most_common(12),
        "speakers": analysis.by_speaker.most_common(),
        "categories": {
            name: [
                {
                    "time": msg.timestamp.isoformat(sep=" ", timespec="minutes"),
                    "speaker": msg.speaker,
                    "content": msg.content,
                }
                for msg in items
            ]
            for name, items in sorted(analysis.categories.items())
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_deepseek_report(
    messages: list[Message],
    top_messages: int,
    api_key: str | None = None,
    model: str = DEFAULT_DEEPSEEK_MODEL,
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
    thinking_enabled: bool = False,
    reasoning_effort: str = "medium",
    max_input_chars: int = 60000,
    timeout: int = 90,
    parse_result: ParseResult | None = None,
) -> str:
    resolved_key = (api_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not resolved_key:
        raise ValueError("请提供 DeepSeek API Key，或设置环境变量 DEEPSEEK_API_KEY。")
    if max_input_chars < 1000:
        raise ValueError("max_input_chars 至少需要 1000。")
    if not messages:
        return build_report(messages, top_messages, parse_result)

    analysis = analyze_messages(messages)
    model_context = build_model_context(messages, top_messages)
    transcript, omitted_count = format_transcript(messages, max_input_chars)
    prompt = build_deepseek_prompt(model_context, transcript, omitted_count, analysis)
    options = DeepSeekOptions(
        api_key=resolved_key,
        model=DEFAULT_DEEPSEEK_MODEL,
        base_url=base_url or DEFAULT_DEEPSEEK_BASE_URL,
        thinking_enabled=thinking_enabled,
        reasoning_effort=normalize_reasoning_effort(reasoning_effort),
        max_input_chars=max_input_chars,
        timeout=timeout,
    )
    return call_deepseek_chat(options, prompt)


def format_transcript(messages: list[Message], max_chars: int) -> tuple[str, int]:
    all_lines = [format_transcript_line(msg) for msg in sorted(messages, key=lambda item: item.timestamp)]
    lines: list[str] = []
    used = 0
    for line in all_lines:
        next_used = used + len(line) + 1
        if next_used > max_chars:
            break
        lines.append(line)
        used = next_used

    if len(lines) == len(all_lines):
        return "\n".join(lines), 0

    return format_transcript_head_tail(all_lines, max_chars)


def format_transcript_line(msg: Message) -> str:
    content = msg.content.replace("\n", " / ")
    return f"[{msg.timestamp:%Y-%m-%d %H:%M}] {msg.speaker}: {content}"


def format_transcript_head_tail(all_lines: list[str], max_chars: int) -> tuple[str, int]:
    if not all_lines:
        return "", 0

    omitted_marker_template = "\n... 中间省略 {count} 条消息 ...\n"
    marker_for_budget = omitted_marker_template.format(count=len(all_lines)).strip()
    available = max_chars - len(marker_for_budget) - 2
    if available <= 0:
        return truncate_single_transcript_line(all_lines[-1], max_chars), len(all_lines) - 1

    head_budget = max(0, available // 2)
    tail_budget = max(0, available - head_budget)
    head: list[str] = []
    tail: list[str] = []
    head_used = 0
    tail_used = 0
    head_index = 0
    tail_index = len(all_lines)

    while head_index < tail_index:
        line = all_lines[head_index]
        cost = len(line) + 1
        if head and head_used + cost > head_budget:
            break
        if not head and cost > head_budget:
            break
        head.append(line)
        head_used += cost
        head_index += 1

    while tail_index > head_index:
        line = all_lines[tail_index - 1]
        cost = len(line) + 1
        if tail and tail_used + cost > tail_budget:
            break
        if not tail and cost > tail_budget:
            break
        tail.append(line)
        tail_used += cost
        tail_index -= 1

    if not head and not tail:
        return truncate_single_transcript_line(all_lines[-1], max_chars), len(all_lines) - 1

    selected_tail = list(reversed(tail))
    omitted_count = max(0, tail_index - head_index)
    if omitted_count:
        marker = omitted_marker_template.format(count=omitted_count).strip()
        return "\n".join([*head, marker, *selected_tail]), omitted_count
    return "\n".join([*head, *selected_tail]), 0


def truncate_single_transcript_line(line: str, max_chars: int) -> str:
    if len(line) <= max_chars:
        return line
    if max_chars <= 3:
        return line[:max_chars]
    return line[: max_chars - 3] + "..."


def build_deepseek_prompt(model_context: str, transcript: str, omitted_count: int, analysis: Analysis) -> str:
    warning = ""
    if omitted_count:
        warning = f"\n注意：由于输入长度限制，原始聊天记录中间有 {omitted_count} 条消息未发送给模型，开头和结尾已保留。"

    category_counts = {
        name: len(items)
        for name, items in sorted(analysis.categories.items())
    }
    return f"""原始聊天记录：
{transcript}

任务：请根据上面的微信聊天记录生成一份中文 Markdown 摘要。

要求：
- 只总结聊天内容，不编造聊天里没有出现的事实。
- 如果某项信息没有明确出现，请写“未明确”。
- 不要输出推理过程。
- 只输出以下五个二级标题，不要新增其他标题：
  1. 聊天时间范围
  2. 参与人物
  3. 主要事件
  4. 核心摘要
  5. 原文依据
- “聊天时间范围”写清起止时间。
- “参与人物”列出主要发言人及其角色或贡献；角色不明确时写“未明确”。
- “主要事件”按时间顺序概括发生了什么。
- “核心摘要”用 3 到 6 条总结最重要的信息。
- “原文依据”引用关键原文，保留时间和发言人。

分类计数：
{json.dumps(category_counts, ensure_ascii=False)}
{warning}

本地规则辅助信息：
{model_context}
"""


def normalize_reasoning_effort(value: str) -> str:
    normalized = (value or "medium").strip().lower()
    allowed = {"low", "medium", "high", "max", "xhigh"}
    return normalized if normalized in allowed else "medium"


def call_deepseek_chat(options: DeepSeekOptions, prompt: str) -> str:
    return request_deepseek_chat(
        options,
        prompt,
        system_prompt="你是严谨的中文聊天记录摘要助手。只根据用户提供的聊天记录总结。",
        max_tokens=3000,
    )


def request_deepseek_chat(
    options: DeepSeekOptions,
    prompt: str,
    *,
    system_prompt: str,
    max_tokens: int,
) -> str:
    endpoint = f"{options.base_url.rstrip('/')}{DEEPSEEK_CHAT_PATH}"
    payload: dict[str, object] = {
        "model": options.model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }
    if options.thinking_enabled:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = options.reasoning_effort
    else:
        payload["temperature"] = 0.2
        if options.model in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            payload["thinking"] = {"type": "disabled"}

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {options.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=options.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API 请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 DeepSeek API：{exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"DeepSeek API 返回格式异常：{data}") from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek API 返回了空摘要。")
    return content.strip() + "\n"


def test_deepseek_connection(
    api_key: str | None,
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
    *,
    timeout: int = 15,
) -> str:
    resolved_key = (api_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not resolved_key:
        raise ValueError("请先填写 DeepSeek API Key。")
    options = DeepSeekOptions(
        api_key=resolved_key,
        model=DEFAULT_DEEPSEEK_MODEL,
        base_url=base_url or DEFAULT_DEEPSEEK_BASE_URL,
        thinking_enabled=False,
        timeout=timeout,
    )
    return request_deepseek_chat(
        options,
        "仅回复 OK",
        system_prompt="你是 API 连通性测试助手。严格按用户要求回复。",
        max_tokens=8,
    )


def read_text(path: Path, encoding: str) -> ReadResult:
    data = path.read_bytes()
    return read_text_bytes(data, encoding)


def read_text_bytes(data: bytes, encoding: str) -> ReadResult:
    if encoding.lower() != "auto":
        return ReadResult(text=data.decode(encoding), encoding=encoding)

    errors: list[str] = []
    for candidate in candidate_encodings(data):
        try:
            return ReadResult(text=data.decode(candidate), encoding=candidate)
        except UnicodeDecodeError as exc:
            errors.append(f"{candidate}: {exc}")
    raise UnicodeDecodeError("auto", data, 0, min(16, len(data)), "; ".join(errors))


def candidate_encodings(data: bytes) -> tuple[str, ...]:
    if data.startswith(b"\xef\xbb\xbf"):
        return ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16-le")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return ("utf-16", "utf-16-le", "utf-8", "utf-8-sig", "gb18030")
    sample = data[:200]
    if sample and sample.count(b"\x00") / len(sample) > 0.2:
        return ("utf-16-le", "utf-16", "utf-8", "utf-8-sig", "gb18030")
    return AUTO_ENCODINGS


def parse_date_filter(value: str | None, end_of_day: bool = False) -> dt.datetime | None:
    if not value:
        return None
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
        parsed = dt.datetime.strptime(value.replace("/", "-"), "%Y-%m-%d")
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59)
        return parsed
    return parse_timestamp(value)


def filter_messages(
    messages: list[Message],
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    speakers: list[str],
) -> list[Message]:
    selected = messages
    if date_from:
        selected = [msg for msg in selected if msg.timestamp >= date_from]
    if date_to:
        selected = [msg for msg in selected if msg.timestamp <= date_to]
    if speakers:
        wanted = set(speakers)
        selected = [msg for msg in selected if msg.speaker in wanted]
    return selected


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize exported WeChat chat records.")
    parser.add_argument("input", type=Path, help="input chat text file")
    parser.add_argument("-o", "--output", type=Path, help="write report to this path")
    parser.add_argument("--top-messages", type=int, default=8, help="max messages in each extracted section")
    parser.add_argument("--encoding", default="auto", help="input encoding, default: auto")
    parser.add_argument("--date-from", help="only include messages at or after this date/time")
    parser.add_argument("--date-to", help="only include messages at or before this date/time")
    parser.add_argument("--speaker", action="append", default=[], help="only include this speaker; can be repeated")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="output format")
    parser.add_argument("--engine", choices=("local", "deepseek"), default="local", help="summary engine")
    parser.add_argument("--deepseek-api-key", help="DeepSeek API key; falls back to DEEPSEEK_API_KEY")
    parser.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_MODEL, help="DeepSeek model name")
    parser.add_argument("--deepseek-base-url", default=DEFAULT_DEEPSEEK_BASE_URL, help="DeepSeek API base URL")
    parser.add_argument("--deepseek-thinking", action="store_true", help="enable DeepSeek thinking mode")
    parser.add_argument(
        "--deepseek-reasoning-effort",
        default="medium",
        choices=("low", "medium", "high", "max", "xhigh"),
        help="DeepSeek thinking effort, default: medium",
    )
    parser.add_argument("--max-input-chars", type=int, default=60000, help="max transcript chars sent to DeepSeek")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
