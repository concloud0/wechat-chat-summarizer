"""Command line entrypoint using the shared service layer."""

from __future__ import annotations

import sys

from . import service
from . import summarizer


def parse_args(argv: list[str]):
    return summarizer.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.top_messages < 1:
        print("--top-messages must be greater than 0", file=sys.stderr)
        return 2
    if not args.input.exists():
        print(f"input file not found: {args.input}", file=sys.stderr)
        return 2

    request = service.SummaryRequest(
        encoding=args.encoding,
        output_format=args.format,
        date_from=args.date_from,
        date_to=args.date_to,
        speakers=tuple(args.speaker),
        top_messages=args.top_messages,
        engine=args.engine,
        deepseek_api_key=args.deepseek_api_key,
        deepseek_base_url=args.deepseek_base_url,
        deepseek_thinking=args.deepseek_thinking,
        deepseek_reasoning_effort=args.deepseek_reasoning_effort,
        max_input_chars=args.max_input_chars,
    )

    try:
        response = service.summarize_file(args.input, request)
    except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.output:
        args.output.write_text(response.report, encoding="utf-8")
        print(f"wrote {args.output} using {response.encoding}")
    else:
        print(response.report)
    return 0
