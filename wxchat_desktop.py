#!/usr/bin/env python3
"""Desktop application entrypoint."""

from __future__ import annotations

import sys

from wxchat_app.desktop import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
