#!/usr/bin/env python3
"""Compatibility wrapper for the legacy browser UI."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    from wxchat_app.webapp import main

    raise SystemExit(main(sys.argv[1:]))

from wxchat_app import webapp as _impl

sys.modules[__name__] = _impl
