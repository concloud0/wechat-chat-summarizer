"""Compatibility wrapper for `wxchat_app.wechat_cli_bridge`."""

from __future__ import annotations

import sys

from wxchat_app import wechat_cli_bridge as _impl

sys.modules[__name__] = _impl
