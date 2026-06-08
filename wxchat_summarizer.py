#!/usr/bin/env python3
"""Compatibility wrapper for the chat summarizer CLI and module."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    from wxchat_app.cli import main

    raise SystemExit(main(sys.argv[1:]))

from wxchat_app import summarizer as _impl

sys.modules[__name__] = _impl
