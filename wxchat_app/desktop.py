"""Tkinter desktop UI for the WeChat chat summarizer."""

from __future__ import annotations

import argparse
import calendar
import ctypes
import datetime as dt
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import settings as app_settings
from . import service
from . import summarizer
from . import wechat_cli_bridge
from .version import APP_NAME, APP_NAME_EN, APP_VERSION


TaskCallback = Callable[[object], None]

FONT_FAMILY = "Microsoft YaHei UI"
UI_FONT = (FONT_FAMILY, 9)
TITLE_FONT = (FONT_FAMILY, 17, "bold")
SECTION_FONT = (FONT_FAMILY, 9, "bold")
METRIC_FONT = ("Segoe UI", 10)

BG = "#f7f8fa"
PANEL = "#ffffff"
SURFACE = "#f7f8fa"
SIDEBAR = "#f4f5f7"
TEXT = "#111827"
MUTED = "#6b7280"
SUBTLE = "#9ca3af"
LINE = "#e5e7eb"
ACCENT = "#5e6ad2"
ACCENT_SOFT = "#eef0ff"
ACCENT_DARK = "#4f46c7"


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative_path


class LinearButton(tk.Button):
    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None] | None = None, *, primary: bool = False, width: int | None = None) -> None:
        bg = ACCENT if primary else "#ffffff"
        fg = "#ffffff" if primary else TEXT
        active_bg = ACCENT_DARK if primary else "#f3f4f6"
        super().__init__(
            master,
            text=text,
            command=command,
            width=width or 0,
            bd=0,
            relief="flat",
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            disabledforeground="#9ca3af",
            font=(FONT_FAMILY, 9, "bold") if primary else UI_FONT,
            padx=10,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=ACCENT if primary else LINE,
            highlightcolor=ACCENT if primary else LINE,
        )


class LinearField(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        variable: tk.StringVar,
        *,
        show: str | None = None,
        readonly: bool = False,
        width: int | None = None,
    ) -> None:
        super().__init__(master, bg="#ffffff", highlightbackground=LINE, highlightcolor=ACCENT, highlightthickness=1)
        self.variable = variable
        self.masked = bool(show)
        self.entry = tk.Entry(
            self,
            textvariable=variable,
            show=show or "",
            width=width or 0,
            bd=0,
            relief="flat",
            bg="#ffffff",
            fg=TEXT,
            insertbackground=ACCENT,
            readonlybackground="#ffffff",
            disabledbackground="#ffffff",
            disabledforeground=MUTED,
            font=UI_FONT,
            cursor="xterm",
            takefocus=True,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        self.columnconfigure(0, weight=1)
        self.entry.bind("<FocusIn>", lambda _event: self.configure(highlightbackground=ACCENT))
        self.entry.bind("<FocusOut>", lambda _event: self.configure(highlightbackground=LINE))
        self.bind("<Button-1>", self.focus_entry)
        if readonly:
            self.entry.configure(state="readonly")

    def focus_entry(self, _event: tk.Event | None = None) -> None:
        if str(self.entry.cget("state")) == "normal":
            self.entry.focus_set()
            self.entry.icursor(tk.END)

    def cget(self, key: str) -> object:
        if key == "state":
            return self.entry.cget("state")
        return super().cget(key)

    def configure(self, cnf: dict[str, object] | None = None, **kwargs: object) -> object:
        options = dict(cnf or {})
        options.update(kwargs)
        state = options.pop("state", None)
        show = options.pop("show", None)
        if state is not None:
            self.entry.configure(state=state)
        if show is not None:
            self.entry.configure(show=show)
        if options:
            return super().configure(options)
        return None

    config = configure

    def set_masked(self, masked: bool) -> None:
        self.masked = masked
        self.entry.configure(show="*" if masked else "")


class LinearSelect(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        variable: tk.StringVar,
        values: tuple[str, ...] | list[str],
        *,
        command: Callable[[object], None] | None = None,
        width: int | None = None,
    ) -> None:
        super().__init__(master, bg="#ffffff", highlightbackground=LINE, highlightcolor=ACCENT, highlightthickness=1, cursor="hand2")
        self.variable = variable
        self.values = list(values)
        self.command = command
        self._state = "normal"
        self.display_var = tk.StringVar(value=variable.get())
        self.label = tk.Label(self, textvariable=self.display_var, anchor="w", bg="#ffffff", fg=TEXT, font=UI_FONT, width=width or 0)
        self.label.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        self.caret = tk.Label(self, text="v", bg="#ffffff", fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.caret.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=6)
        self.columnconfigure(0, weight=1)
        for widget in (self, self.label, self.caret):
            widget.bind("<Button-1>", self.open_menu)
        self.variable.trace_add("write", lambda *_: self.sync_display())
        self.sync_display()

    def sync_display(self) -> None:
        self.display_var.set(self.variable.get())

    def cget(self, key: str) -> object:
        if key == "state":
            return self._state
        if key == "values":
            return tuple(self.values)
        return super().cget(key)

    def configure(self, cnf: dict[str, object] | None = None, **kwargs: object) -> object:
        options = dict(cnf or {})
        options.update(kwargs)
        if "values" in options:
            self.values = list(options.pop("values") or [])
            if self.variable.get() not in self.values:
                self.variable.set(self.values[0] if self.values else "")
        if "state" in options:
            self._state = str(options.pop("state"))
            muted = self._state == "disabled"
            self.label.configure(fg=SUBTLE if muted else TEXT)
            self.caret.configure(fg=SUBTLE if muted else MUTED)
            self.configure_cursor("arrow" if muted else "hand2")
        if options:
            return super().configure(options)
        return None

    config = configure

    def configure_cursor(self, cursor: str) -> None:
        for widget in (self, self.label, self.caret):
            widget.configure(cursor=cursor)

    def open_menu(self, _event: tk.Event | None = None) -> None:
        if self._state == "disabled" or not self.values:
            return
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=LINE)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 3
        width = max(self.winfo_width(), 160)
        height = min(max(len(self.values), 1) * 28 + 2, 220)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        listbox = tk.Listbox(
            popup,
            bd=0,
            highlightthickness=0,
            activestyle="none",
            bg="#ffffff",
            fg=TEXT,
            selectbackground=ACCENT_SOFT,
            selectforeground=TEXT,
            font=UI_FONT,
            exportselection=False,
        )
        listbox.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(0, weight=1)
        for value in self.values:
            listbox.insert(tk.END, value)
        if self.variable.get() in self.values:
            index = self.values.index(self.variable.get())
            listbox.selection_set(index)
            listbox.activate(index)

        def choose(_event: tk.Event | None = None) -> None:
            selection = listbox.curselection()
            if selection:
                self.select_value(self.values[selection[0]])
            popup.destroy()

        def dismiss(_event: tk.Event | None = None) -> None:
            popup.destroy()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        popup.bind("<Escape>", dismiss)
        popup.focus_force()
        listbox.focus_set()

    def select_value(self, value: str) -> None:
        if value not in self.values:
            return
        self.variable.set(value)
        if self.command:
            self.command(None)


class SearchableSelect(LinearSelect):
    def __init__(
        self,
        master: tk.Misc,
        variable: tk.StringVar,
        values: tuple[str, ...] | list[str],
        *,
        search_texts: dict[str, str] | None = None,
        command: Callable[[object], None] | None = None,
        width: int | None = None,
    ) -> None:
        self.search_texts = search_texts or {}
        super().__init__(master, variable, values, command=command, width=width)

    def configure(self, cnf: dict[str, object] | None = None, **kwargs: object) -> object:
        options = dict(cnf or {})
        options.update(kwargs)
        search_texts = options.pop("search_texts", None)
        if search_texts is not None:
            self.search_texts = dict(search_texts)
        return super().configure(options)

    config = configure

    def filtered_values(self, query: str) -> list[str]:
        normalized = query.strip().casefold()
        if not normalized:
            return list(self.values)
        return [
            value
            for value in self.values
            if normalized in self.search_texts.get(value, value).casefold()
        ]

    def open_menu(self, _event: tk.Event | None = None) -> None:
        if self._state == "disabled" or not self.values:
            return
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=LINE)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 3
        width = max(self.winfo_width(), 240)
        popup.geometry(f"{width}x260+{x}+{y}")

        body = tk.Frame(popup, bg="#ffffff")
        body.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        query_var = tk.StringVar()
        search = tk.Entry(
            body,
            textvariable=query_var,
            bd=0,
            relief="flat",
            bg="#f7f8fa",
            fg=TEXT,
            insertbackground=ACCENT,
            font=UI_FONT,
        )
        search.grid(row=0, column=0, sticky="ew", padx=8, pady=8, ipady=6)
        listbox = tk.Listbox(
            body,
            bd=0,
            highlightthickness=0,
            activestyle="none",
            bg="#ffffff",
            fg=TEXT,
            selectbackground=ACCENT_SOFT,
            selectforeground=TEXT,
            font=UI_FONT,
            exportselection=False,
        )
        listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        visible_values: list[str] = []

        def refresh(*_args: object) -> None:
            nonlocal visible_values
            visible_values = self.filtered_values(query_var.get())
            listbox.delete(0, tk.END)
            if visible_values:
                listbox.configure(fg=TEXT)
                for value in visible_values:
                    listbox.insert(tk.END, value)
                listbox.selection_set(0)
                listbox.activate(0)
            else:
                listbox.insert(tk.END, "没有匹配的会话")
                listbox.configure(fg=MUTED)

        def choose(_event: tk.Event | None = None) -> str:
            if visible_values:
                selection = listbox.curselection()
                index = selection[0] if selection else 0
                self.select_value(visible_values[index])
                popup.destroy()
            return "break"

        def dismiss(_event: tk.Event | None = None) -> str:
            popup.destroy()
            return "break"

        query_var.trace_add("write", refresh)
        search.bind("<Down>", lambda _event: (listbox.focus_set(), "break")[1])
        search.bind("<Return>", choose)
        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        popup.bind("<Escape>", dismiss)
        refresh()
        popup.focus_force()
        search.focus_set()


class LinearToggle(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        variable: tk.BooleanVar,
    ) -> None:
        super().__init__(master, bg=SIDEBAR, cursor="hand2")
        self.variable = variable
        self._state = "normal"
        self.label = tk.Label(self, text=text, bg=SIDEBAR, fg=TEXT, font=UI_FONT, cursor="hand2")
        self.label.grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(
            self,
            width=34,
            height=18,
            bg=SIDEBAR,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.grid(row=0, column=1, sticky="e")
        self.columnconfigure(0, weight=1)
        for widget in (self, self.label, self.canvas):
            widget.bind("<Button-1>", self.toggle)
        self.variable.trace_add("write", lambda *_: self.render())
        self.render()

    def cget(self, key: str) -> object:
        if key == "state":
            return self._state
        return super().cget(key)

    def configure(self, cnf: dict[str, object] | None = None, **kwargs: object) -> object:
        options = dict(cnf or {})
        options.update(kwargs)
        if "state" in options:
            self._state = str(options.pop("state"))
            cursor = "arrow" if self._state == "disabled" else "hand2"
            self.label.configure(fg=SUBTLE if self._state == "disabled" else TEXT)
            for widget in (self, self.label, self.canvas):
                widget.configure(cursor=cursor)
            self.render()
        if options:
            return super().configure(options)
        return None

    config = configure

    def toggle(self, _event: tk.Event | None = None) -> None:
        if self._state != "disabled":
            self.variable.set(not self.variable.get())

    def render(self) -> None:
        enabled = self.variable.get()
        track = ACCENT if enabled and self._state != "disabled" else "#d1d5db"
        knob_x = 24 if enabled else 10
        self.canvas.delete("all")
        self.canvas.create_oval(1, 1, 17, 17, fill=track, outline=track)
        self.canvas.create_oval(17, 1, 33, 17, fill=track, outline=track)
        self.canvas.create_rectangle(9, 1, 25, 17, fill=track, outline=track)
        self.canvas.create_oval(knob_x - 6, 3, knob_x + 6, 15, fill="#ffffff", outline="#ffffff")


def enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        return


def configure_tk_scaling(root: tk.Tk) -> float:
    dpi = float(root.winfo_fpixels("1i") or 96.0)
    root.tk.call("tk", "scaling", dpi / 72.0)
    return max(1.0, min(dpi / 96.0, 2.5))


class DateField(ttk.Frame):
    def __init__(self, master: tk.Misc, label: str, variable: tk.StringVar) -> None:
        super().__init__(master, style="Surface.TFrame")
        self.variable = variable
        ttk.Label(self, text=label, style="FieldLabel.TLabel", width=9).grid(row=0, column=0, sticky="w", padx=(0, 8))
        LinearField(self, variable, readonly=True, width=9).grid(row=0, column=1, sticky="ew")
        LinearButton(self, "选择", self.open_picker, width=5).grid(row=0, column=2, padx=(6, 0))
        LinearButton(self, "清除", lambda: variable.set(""), width=5).grid(row=0, column=3, padx=(6, 0))
        self.columnconfigure(1, weight=1)

    def open_picker(self) -> None:
        DatePickerDialog(self, self.variable)


class DatePickerDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, variable: tk.StringVar) -> None:
        super().__init__(master)
        self.variable = variable
        self.title("选择日期")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        try:
            current = dt.datetime.strptime(variable.get(), "%Y-%m-%d").date()
        except ValueError:
            current = dt.date.today()
        self.year = current.year
        self.month = current.month

        self.selected_value = variable.get()
        self.header = ttk.Label(self, anchor="center", font=SECTION_FONT, style="Panel.TLabel")
        LinearButton(self, "上月", self.previous_month, width=5).grid(row=0, column=0, padx=8, pady=10)
        self.header.grid(row=0, column=1, columnspan=5, sticky="ew", padx=6, pady=10)
        LinearButton(self, "下月", self.next_month, width=5).grid(row=0, column=6, padx=8, pady=10)
        self.days_frame = ttk.Frame(self, style="Panel.TFrame")
        self.days_frame.grid(row=1, column=0, columnspan=7, padx=10, pady=(0, 10))
        LinearButton(self, "今天", self.select_today).grid(row=2, column=0, columnspan=7, sticky="ew", padx=10, pady=(0, 10))
        self.render_days()

    def previous_month(self) -> None:
        if self.month == 1:
            self.year -= 1
            self.month = 12
        else:
            self.month -= 1
        self.render_days()

    def next_month(self) -> None:
        if self.month == 12:
            self.year += 1
            self.month = 1
        else:
            self.month += 1
        self.render_days()

    def render_days(self) -> None:
        for child in self.days_frame.winfo_children():
            child.destroy()
        self.header.configure(text=f"{self.year}-{self.month:02d}")

        for col, label in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            ttk.Label(self.days_frame, text=label, anchor="center", width=4, style="Muted.TLabel").grid(row=0, column=col, padx=2, pady=2)

        month_days = calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        for row_index, week in enumerate(month_days, start=1):
            for col_index, day in enumerate(week):
                if day == 0:
                    ttk.Label(self.days_frame, text="", width=4, style="Panel.TLabel").grid(row=row_index, column=col_index, padx=2, pady=2)
                    continue
                LinearButton(
                    self.days_frame,
                    str(day),
                    lambda value=day: self.select_day(value),
                    primary=f"{self.year}-{self.month:02d}-{day:02d}" == self.selected_value,
                    width=4,
                ).grid(row=row_index, column=col_index, padx=2, pady=2)

    def select_day(self, day: int) -> None:
        self.variable.set(f"{self.year}-{self.month:02d}-{day:02d}")
        self.destroy()

    def select_today(self) -> None:
        today = dt.date.today()
        self.variable.set(today.isoformat())
        self.destroy()


class DesktopApp(ttk.Frame):
    def __init__(
        self,
        master: tk.Tk,
        *,
        config_path: Path | None = None,
        secret_protector: app_settings.SecretProtector | None = None,
    ) -> None:
        self.scale = configure_tk_scaling(master)
        self.style = ttk.Style(master)
        self.configure_styles()
        super().__init__(master, padding=0, style="App.TFrame")
        self.master = master
        self.settings_store = app_settings.SettingsStore(config_path, secret_protector)
        saved = self.settings_store.load()
        self.task_queue: queue.Queue[tuple[str, object, TaskCallback | None]] = queue.Queue()
        self.latest_response: service.SummaryResponse | None = None
        self.wechat_sessions: list[wechat_cli_bridge.WechatSession] = []
        self.busy_widgets: list[tk.Widget] = []
        self._busy_previous_states: dict[tk.Widget, str] = {}
        self._syncing_dates = False
        self._settings_ready = False
        self._settings_after_id: str | None = None
        self._save_status_after_id: str | None = None
        self._closing = False
        self._source_buttons: list[tk.Radiobutton] = []
        self._api_key_visible = False
        self._markdown_preview_mode = saved.preview_mode

        self.source_var = tk.StringVar(value=saved.source)
        self.file_path_var = tk.StringVar()
        self.date_from_var = tk.StringVar(value=saved.date_from)
        self.date_to_var = tk.StringVar(value=saved.date_to)
        self.speakers_var = tk.StringVar(value=saved.speakers)
        self.engine_var = tk.StringVar(value=saved.engine)
        self.encoding_var = tk.StringVar(value=saved.encoding)
        self.format_var = tk.StringVar(value=saved.output_format)
        self.top_messages_var = tk.StringVar(value=saved.top_messages)
        self.deepseek_key_var = tk.StringVar(value=saved.deepseek_api_key)
        self.deepseek_base_url_var = tk.StringVar(value=saved.deepseek_base_url)
        self.deepseek_thinking_var = tk.BooleanVar(value=saved.deepseek_thinking)
        self.deepseek_effort_var = tk.StringVar(value=saved.deepseek_effort)
        self.max_input_chars_var = tk.StringVar(value=saved.max_input_chars)
        self.wechat_limit_var = tk.StringVar(value=saved.wechat_limit)
        self.wechat_session_limit_var = tk.StringVar(value=saved.wechat_session_limit)
        self.advanced_expanded_var = tk.BooleanVar(value=saved.advanced_expanded)
        self.preview_mode_var = tk.StringVar(value=saved.preview_mode)
        self.wechat_session_var = tk.StringVar()

        self.status_var = tk.StringVar(value="请选择聊天记录或微信会话。")
        self.save_status_var = tk.StringVar(value="")
        self.workspace_title_var = tk.StringVar(value="准备生成摘要")
        self.workspace_subtitle_var = tk.StringVar(value="选择聊天记录后，摘要会显示在这里。")
        self.meta_var = tk.StringVar(value="消息 0 · 成员 0 · 编码 - · 未识别 0")
        self.message_count_var = tk.StringVar(value="0")
        self.speaker_count_var = tk.StringVar(value="0")
        self.encoding_used_var = tk.StringVar(value="-")
        self.ignored_lines_var = tk.StringVar(value="0")

        self.create_widgets()
        self.date_from_var.trace_add("write", lambda *_: self.sync_date_bounds("from"))
        self.date_to_var.trace_add("write", lambda *_: self.sync_date_bounds("to"))
        self.bind_settings_traces()
        self.status_var.trace_add("write", lambda *_: self.update_status_indicator())
        self.update_source_mode()
        self.update_engine_mode()
        self.update_advanced_mode()
        self.update_preview_mode()
        self.set_result_actions_enabled(False)
        self.update_status_indicator()
        self._settings_ready = True
        self.master.protocol("WM_DELETE_WINDOW", self.close)

    def configure_styles(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(".", font=UI_FONT)
        self.style.configure("App.TFrame", background=BG)
        self.style.configure("Panel.TFrame", background=PANEL)
        self.style.configure("Surface.TFrame", background=SIDEBAR)
        self.style.configure("Sidebar.TFrame", background=SIDEBAR)
        self.style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        self.style.configure("Surface.TLabel", background=SIDEBAR, foreground=TEXT)
        self.style.configure("Sidebar.TLabel", background=SIDEBAR, foreground=TEXT)
        self.style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        self.style.configure("SurfaceMuted.TLabel", background=SIDEBAR, foreground=MUTED)
        self.style.configure("Title.TLabel", background=PANEL, foreground=TEXT, font=TITLE_FONT)
        self.style.configure("AppTitle.TLabel", background=BG, foreground=TEXT, font=(FONT_FAMILY, 12, "bold"))
        self.style.configure("Section.TLabel", background=SIDEBAR, foreground=TEXT, font=SECTION_FONT)
        self.style.configure("FieldLabel.TLabel", background=SIDEBAR, foreground=MUTED, font=(FONT_FAMILY, 8, "bold"))
        self.style.configure("MetricValue.TLabel", background=PANEL, foreground=TEXT, font=METRIC_FONT)
        self.style.configure("MetricLabel.TLabel", background=PANEL, foreground=MUTED, font=(FONT_FAMILY, 8))
        self.style.configure("TEntry", fieldbackground="#ffffff", bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=(self.px(8), self.px(5)))
        self.style.configure("TCombobox", fieldbackground="#ffffff", bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=(self.px(8), self.px(5)))
        self.style.configure("TCheckbutton", background=SIDEBAR, foreground=TEXT)
        self.style.configure("TRadiobutton", background=SIDEBAR, foreground=TEXT)
        self.style.configure("TButton", padding=(self.px(11), self.px(6)), borderwidth=1, relief="flat", background="#ffffff", foreground=TEXT)
        self.style.map("TButton", background=[("active", "#f3f4f6")])
        self.style.configure("Subtle.TButton", padding=(self.px(10), self.px(5)), background="#ffffff", foreground=TEXT, bordercolor=LINE)
        self.style.configure("Primary.TButton", padding=(self.px(14), self.px(9)), background=ACCENT, foreground="#ffffff", bordercolor=ACCENT, font=(FONT_FAMILY, 10, "bold"))
        self.style.map("Primary.TButton", background=[("active", ACCENT_DARK), ("disabled", "#b8bde8")], foreground=[("disabled", "#f3f4ff")])
        self.style.configure("Date.TButton", padding=(self.px(5), self.px(5)), background="#ffffff", foreground=TEXT, bordercolor=LINE)
        self.style.configure("DateSelected.TButton", padding=(self.px(5), self.px(5)), background=ACCENT, foreground="#ffffff", bordercolor=ACCENT)
        self.style.map("DateSelected.TButton", background=[("active", ACCENT_DARK)])
        self.style.configure("Segment.TRadiobutton", background=SIDEBAR, foreground=TEXT, padding=(self.px(10), self.px(6)))

    def px(self, value: int | float) -> int:
        return max(1, int(round(value * self.scale)))

    def geometry_px(self, width: int, height: int) -> str:
        return f"{width}x{height}"

    def create_widgets(self) -> None:
        self.grid(sticky="nsew")
        self.master.configure(bg=BG)
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.build_appbar()
        self.build_shell()

    def build_appbar(self) -> None:
        appbar = ttk.Frame(self, style="App.TFrame", padding=(self.px(22), self.px(12), self.px(22), self.px(10)))
        appbar.grid(row=0, column=0, sticky="ew")
        appbar.columnconfigure(1, weight=1)

        mark_size = self.px(24)
        mark = tk.Canvas(appbar, width=mark_size, height=mark_size, bg=BG, highlightthickness=0)
        mark.grid(row=0, column=0, sticky="w", padx=(0, self.px(10)))
        mark.create_rectangle(self.px(3), self.px(3), self.px(21), self.px(21), fill=ACCENT, outline=ACCENT)
        mark.create_text(mark_size // 2, mark_size // 2, text="W", fill="#ffffff", font=("Segoe UI", 10, "bold"))

        title_box = ttk.Frame(appbar, style="App.TFrame")
        title_box.grid(row=0, column=1, sticky="ew")
        ttk.Label(title_box, text="微信聊天摘要工具", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.status_dot = tk.Canvas(title_box, width=self.px(8), height=self.px(8), bg=BG, highlightthickness=0)
        self.status_dot.grid(row=0, column=1, sticky="w", padx=(self.px(14), self.px(6)))
        self.status_label = ttk.Label(title_box, textvariable=self.status_var, style="Muted.TLabel", background=BG)
        self.status_label.grid(row=0, column=2, sticky="w")
        LinearButton(appbar, "关于", self.show_about).grid(row=0, column=2, sticky="e")

    def build_shell(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame", padding=(self.px(22), 0, self.px(22), self.px(22)))
        shell.grid(row=1, column=0, sticky="nsew")
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        self.settings_panel = self.make_inspector(shell, width=self.px(270), padding=self.px(16))
        self.grid_surface(self.settings_panel, row=0, column=0, sticky="ns", padx=(0, self.px(14)))
        self.settings_panel.columnconfigure(0, weight=1)
        self.build_settings_panel(self.settings_panel)

        workspace = self.make_workspace(shell, padding=self.px(22))
        self.grid_surface(workspace, row=0, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(2, weight=1)
        self.build_workspace(workspace)

        self.controls_panel = self.make_inspector(shell, width=self.px(310), padding=self.px(16))
        self.grid_surface(self.controls_panel, row=0, column=2, sticky="ns", padx=(self.px(14), 0))
        self.controls_panel.columnconfigure(0, weight=1)
        self.controls_panel.rowconfigure(4, weight=1)
        self.build_controls_panel(self.controls_panel)

    def make_surface(self, master: tk.Misc, *, padding: int | None = None, bg: str = PANEL) -> tk.Frame:
        padding = self.px(14) if padding is None else padding
        outer = tk.Frame(master, bg=bg, highlightbackground=LINE, highlightthickness=1)
        inner = tk.Frame(outer, bg=bg)
        inner.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        return inner

    def grid_surface(self, surface: tk.Frame, **grid_options: object) -> None:
        outer = getattr(surface, "_surface_outer", surface.master)
        outer.grid(**grid_options)

    def make_inspector(self, master: tk.Misc, *, width: int, padding: int) -> tk.Frame:
        outer = tk.Frame(master, width=width, bg=SIDEBAR, highlightthickness=0)
        outer.grid_propagate(False)
        inner = tk.Frame(outer, bg=SIDEBAR)
        inner.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        setattr(inner, "_surface_outer", outer)
        return inner

    def make_workspace(self, master: tk.Misc, *, padding: int) -> tk.Frame:
        outer = tk.Frame(master, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        inner = tk.Frame(outer, bg=PANEL)
        inner.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        setattr(inner, "_surface_outer", outer)
        return inner

    def build_settings_panel(self, parent: tk.Frame) -> None:
        ttk.Label(parent, text="记录来源", style="Sidebar.TLabel", font=(FONT_FAMILY, 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="选择文本文件或微信会话。", style="Sidebar.TLabel", foreground=MUTED).grid(row=1, column=0, sticky="w", pady=(self.px(2), self.px(12)))

        source_section = ttk.Frame(parent, style="Sidebar.TFrame")
        source_section.grid(row=2, column=0, sticky="ew")
        file_segment = self.make_segment(source_section, "文本文件", "file")
        file_segment.grid(row=1, column=0, sticky="ew")
        wechat_segment = self.make_segment(source_section, "微信会话", "wechat")
        wechat_segment.grid(row=1, column=1, sticky="ew", padx=(self.px(6), 0))
        self._source_buttons = [file_segment, wechat_segment]
        source_section.columnconfigure(0, weight=1)
        source_section.columnconfigure(1, weight=1)

        self.file_frame = self.add_section(parent, "文本文件", 3)
        self.file_frame.columnconfigure(0, weight=1)
        self.track(LinearField(self.file_frame, self.file_path_var, readonly=True)).grid(row=1, column=0, columnspan=2, sticky="ew")
        self.track(LinearButton(self.file_frame, "选择聊天文件", self.choose_file)).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(self.px(8), 0),
        )

        self.wechat_frame = self.add_section(parent, "微信会话", 4)
        self.wechat_frame.columnconfigure(0, weight=1)
        self.track(LinearButton(self.wechat_frame, "检测", self.check_wechat_status)).grid(row=1, column=0, sticky="ew")
        self.track(LinearButton(self.wechat_frame, "刷新会话", self.load_wechat_sessions)).grid(row=1, column=1, sticky="ew", padx=(self.px(8), 0))
        self.wechat_combo = self.track(
            SearchableSelect(
                self.wechat_frame,
                self.wechat_session_var,
                (),
                width=22,
                command=lambda _event: self.on_session_selected(),
            )
        )
        self.wechat_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(self.px(10), 0))
        self.add_labeled_entry(self.wechat_frame, "导出条数", self.wechat_limit_var, 3, 0, columnspan=2)
        self.add_labeled_entry(self.wechat_frame, "会话数量", self.wechat_session_limit_var, 4, 0, columnspan=2)

    def build_controls_panel(self, parent: tk.Frame) -> None:
        ttk.Label(parent, text="摘要设置", style="Sidebar.TLabel", font=(FONT_FAMILY, 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="筛选范围与 DeepSeek 参数。", style="Sidebar.TLabel", foreground=MUTED).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(self.px(2), self.px(8)),
        )

        filter_section = self.add_section(parent, "筛选", 2)
        filter_section.columnconfigure(0, weight=1)
        shortcuts = ttk.Frame(filter_section, style="Sidebar.TFrame")
        shortcuts.grid(row=1, column=0, sticky="ew", pady=(0, self.px(7)))
        for column, (label, days) in enumerate((("全部", 0), ("最近 7 天", 7), ("最近 30 天", 30))):
            button = self.track(LinearButton(shortcuts, label, lambda value=days: self.apply_date_preset(value)))
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else self.px(5), 0))
            shortcuts.columnconfigure(column, weight=1)
        DateField(filter_section, "起始日期", self.date_from_var).grid(row=2, column=0, sticky="ew", pady=(0, self.px(8)))
        DateField(filter_section, "结束日期", self.date_to_var).grid(row=3, column=0, sticky="ew", pady=(0, self.px(8)))
        self.add_labeled_entry(filter_section, "成员筛选", self.speakers_var, 4, 0)
        self.add_labeled_combo(filter_section, "编码", self.encoding_var, ("auto", "utf-8", "gb18030", "utf-16"), 5, 0)
        self.add_labeled_entry(filter_section, "摘录数量", self.top_messages_var, 6, 0)

        engine_section = self.add_section(parent, "摘要引擎", 3)
        engine_section.columnconfigure(0, weight=1)
        self.add_labeled_combo(engine_section, "引擎", self.engine_var, ("local", "deepseek"), 1, 0, command=lambda _: self.update_engine_mode())
        self.add_labeled_combo(engine_section, "输出格式", self.format_var, ("markdown", "json"), 2, 0)
        self.deepseek_frame = ttk.Frame(engine_section, style="Surface.TFrame")
        self.deepseek_frame.grid(row=3, column=0, sticky="ew", pady=(self.px(8), 0))
        self.deepseek_frame.columnconfigure(0, weight=1)
        key_row = ttk.Frame(self.deepseek_frame, style="Sidebar.TFrame")
        key_row.grid(row=0, column=0, sticky="ew", pady=(self.px(5), 0))
        key_row.columnconfigure(1, weight=1)
        ttk.Label(key_row, text="API Key", style="FieldLabel.TLabel", width=9).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, self.px(8)),
        )
        self.deepseek_key_field = self.track(LinearField(key_row, self.deepseek_key_var, show="*"))
        self.deepseek_key_field.grid(row=0, column=1, sticky="ew")
        self.key_visibility_button = self.track(LinearButton(key_row, "显示", self.toggle_api_key_visibility, width=4))
        self.key_visibility_button.grid(row=0, column=2, padx=(self.px(6), 0))
        self.track(LinearToggle(self.deepseek_frame, "思考模式", self.deepseek_thinking_var)).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(self.px(10), self.px(3)),
        )
        self.add_labeled_combo(self.deepseek_frame, "思考深度", self.deepseek_effort_var, ("low", "medium", "high", "max"), 2, 0)
        deepseek_actions = ttk.Frame(self.deepseek_frame, style="Sidebar.TFrame")
        deepseek_actions.grid(row=3, column=0, sticky="ew", pady=(self.px(9), 0))
        deepseek_actions.columnconfigure(0, weight=1)
        deepseek_actions.columnconfigure(1, weight=1)
        self.connection_test_button = self.track(LinearButton(deepseek_actions, "测试连接", self.test_deepseek_connection))
        self.connection_test_button.grid(row=0, column=0, sticky="ew")
        self.advanced_button = self.track(LinearButton(deepseek_actions, "高级设置  >", self.toggle_advanced))
        self.advanced_button.grid(row=0, column=1, sticky="ew", padx=(self.px(6), 0))
        self.advanced_frame = ttk.Frame(self.deepseek_frame, style="Surface.TFrame")
        self.advanced_frame.grid(row=4, column=0, sticky="ew")
        self.advanced_frame.columnconfigure(0, weight=1)
        self.add_labeled_entry(self.advanced_frame, "API Base URL", self.deepseek_base_url_var, 0, 0)
        self.add_labeled_entry(self.advanced_frame, "发送上限", self.max_input_chars_var, 1, 0)

        footer = ttk.Frame(parent, style="Sidebar.TFrame")
        footer.grid(row=5, column=0, sticky="sew", pady=(self.px(12), 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.save_status_var, style="SurfaceMuted.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, self.px(6)),
        )
        self.summarize_button = self.track(LinearButton(footer, "生成摘要", self.summarize, primary=True))
        self.summarize_button.grid(row=1, column=0, sticky="ew")

    def build_workspace(self, parent: tk.Frame) -> None:
        header = ttk.Frame(parent, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, self.px(12)))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.workspace_title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.workspace_subtitle_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(self.px(3), 0))
        self.copy_button = LinearButton(header, "复制", self.copy_report)
        self.copy_button.grid(row=0, column=1, rowspan=2, padx=(self.px(8), 0))
        self.export_button = LinearButton(header, "导出", self.export_report)
        self.export_button.grid(row=0, column=2, rowspan=2, padx=(self.px(8), 0))

        meta = ttk.Frame(parent, style="Panel.TFrame")
        meta.grid(row=1, column=0, sticky="ew", pady=(0, self.px(12)))
        ttk.Label(meta, text="消息", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(meta, textvariable=self.message_count_var, style="MetricValue.TLabel").grid(row=0, column=1, sticky="w", padx=(self.px(5), self.px(14)))
        ttk.Label(meta, text="成员", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(meta, textvariable=self.speaker_count_var, style="MetricValue.TLabel").grid(row=0, column=3, sticky="w", padx=(self.px(5), self.px(14)))
        ttk.Label(meta, text="编码", style="Muted.TLabel").grid(row=0, column=4, sticky="w")
        ttk.Label(meta, textvariable=self.encoding_used_var, style="MetricValue.TLabel").grid(row=0, column=5, sticky="w", padx=(self.px(5), self.px(14)))
        self.ignored_button = LinearButton(meta, "未识别 0", self.show_ignored_lines)
        self.ignored_button.grid(row=0, column=6, sticky="w")
        self.ignored_button.configure(state="disabled", fg=MUTED)

        preview_switch = ttk.Frame(meta, style="Panel.TFrame")
        preview_switch.grid(row=0, column=7, sticky="e")
        meta.columnconfigure(7, weight=1)
        self.reading_button = tk.Radiobutton(
            preview_switch,
            text="阅读",
            variable=self.preview_mode_var,
            value="reading",
            command=self.update_preview_mode,
            indicatoron=False,
            bd=0,
            relief="flat",
            padx=self.px(9),
            pady=self.px(4),
            bg="#ffffff",
            fg=TEXT,
            selectcolor=ACCENT_SOFT,
            activebackground=ACCENT_SOFT,
            font=UI_FONT,
            cursor="hand2",
        )
        self.reading_button.grid(row=0, column=0)
        self.source_button = tk.Radiobutton(
            preview_switch,
            text="源码",
            variable=self.preview_mode_var,
            value="source",
            command=self.update_preview_mode,
            indicatoron=False,
            bd=0,
            relief="flat",
            padx=self.px(9),
            pady=self.px(4),
            bg="#ffffff",
            fg=TEXT,
            selectcolor=ACCENT_SOFT,
            activebackground=ACCENT_SOFT,
            font=UI_FONT,
            cursor="hand2",
        )
        self.source_button.grid(row=0, column=1, padx=(self.px(4), 0))

        preview_shell = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        preview_shell.grid(row=2, column=0, sticky="nsew")
        preview_shell.columnconfigure(0, weight=1)
        preview_shell.rowconfigure(0, weight=1)

        self.output_text = tk.Text(
            preview_shell,
            wrap="word",
            height=28,
            undo=False,
            bg="#ffffff",
            fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            borderwidth=0,
            padx=self.px(22),
            pady=self.px(20),
            font=(FONT_FAMILY, 10),
            spacing1=self.px(2),
            spacing3=self.px(4),
        )
        self.output_text.grid(row=0, column=0, sticky="nsew")
        self.configure_preview_tags()
        preview_shell.bind("<Configure>", self.update_preview_padding)
        self.output_text.insert("1.0", "选择聊天记录后点击“生成摘要”。\n\n可以限制日期、成员，或切换本地规则 / DeepSeek API。")
        self.output_text.configure(fg=MUTED)
        self.output_text.configure(state="disabled")

    def add_section(self, parent: tk.Frame, title: str, row: int) -> ttk.Frame:
        section = ttk.Frame(parent, style="Sidebar.TFrame", padding=(0, self.px(5), 0, self.px(5)))
        section.grid(row=row, column=0, sticky="ew", pady=(0, self.px(2)))
        section.columnconfigure(0, weight=1)
        ttk.Label(section, text=title, style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self.px(6)))
        return section

    def track(self, widget: tk.Widget) -> tk.Widget:
        self.busy_widgets.append(widget)
        return widget

    def add_divider(self, parent: tk.Misc, row: int) -> None:
        divider = tk.Frame(parent, bg=LINE, height=1)
        divider.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(self.px(6), 0))

    def make_segment(self, parent: tk.Misc, text: str, value: str) -> tk.Radiobutton:
        button = tk.Radiobutton(
            parent,
            text=text,
            variable=self.source_var,
            value=value,
            command=self.update_source_mode,
            indicatoron=False,
            bd=0,
            relief="flat",
            padx=self.px(10),
            pady=self.px(6),
            bg="#ffffff",
            fg=TEXT,
            activebackground=ACCENT_SOFT,
            activeforeground=TEXT,
            selectcolor=ACCENT_SOFT,
            font=UI_FONT,
            cursor="hand2",
        )
        self.track(button)
        return button

    def status_meta_text(self) -> str:
        return (
            f"消息 {self.message_count_var.get()} · "
            f"成员 {self.speaker_count_var.get()} · "
            f"编码 {self.encoding_used_var.get()} · "
            f"未识别 {self.ignored_lines_var.get()}"
        )

    def configure_preview_tags(self) -> None:
        self.output_text.tag_configure(
            "h1",
            font=(FONT_FAMILY, 18, "bold"),
            foreground=TEXT,
            spacing1=self.px(12),
            spacing3=self.px(8),
        )
        self.output_text.tag_configure(
            "h2",
            font=(FONT_FAMILY, 14, "bold"),
            foreground=TEXT,
            spacing1=self.px(14),
            spacing3=self.px(6),
        )
        self.output_text.tag_configure(
            "h3",
            font=(FONT_FAMILY, 11, "bold"),
            foreground=TEXT,
            spacing1=self.px(10),
            spacing3=self.px(4),
        )
        self.output_text.tag_configure("bold", font=(FONT_FAMILY, 10, "bold"))
        self.output_text.tag_configure("link", foreground=ACCENT_DARK, underline=True)
        self.output_text.tag_configure(
            "code",
            font=("Consolas", 9),
            background="#f3f4f6",
            foreground="#374151",
        )
        self.output_text.tag_configure(
            "code_block",
            font=("Consolas", 9),
            background="#f7f8fa",
            foreground="#374151",
            lmargin1=self.px(14),
            lmargin2=self.px(14),
            spacing1=self.px(5),
            spacing3=self.px(5),
        )
        self.output_text.tag_configure(
            "bullet",
            lmargin1=self.px(8),
            lmargin2=self.px(28),
            spacing1=self.px(2),
            spacing3=self.px(2),
        )
        self.output_text.tag_configure(
            "quote",
            foreground=MUTED,
            lmargin1=self.px(18),
            lmargin2=self.px(18),
            spacing1=self.px(4),
            spacing3=self.px(4),
        )
        self.output_text.tag_configure("rule", foreground=LINE, spacing1=self.px(6), spacing3=self.px(6))

    def update_preview_padding(self, event: tk.Event) -> None:
        available = max(1, int(event.width))
        horizontal = max(self.px(22), (available - self.px(900)) // 2)
        self.output_text.configure(padx=horizontal)

    def insert_inline_markdown(self, text: str, base_tag: str | None = None) -> None:
        pattern = re.compile(r"(\*\*.+?\*\*|`.+?`|\[[^\]]+\]\([^)]+\))")
        for part in pattern.split(text):
            if not part:
                continue
            tags: tuple[str, ...] = (base_tag,) if base_tag else ()
            if part.startswith("**") and part.endswith("**"):
                tags += ("bold",)
                part = part[2:-2]
            elif part.startswith("`") and part.endswith("`"):
                tags += ("code",)
                part = part[1:-1]
            elif re.fullmatch(r"\[[^\]]+\]\([^)]+\)", part):
                tags += ("link",)
                part = part[1 : part.index("]")]
            self.output_text.insert(tk.END, part, tags)

    def render_markdown(self, markdown: str) -> None:
        in_code_block = False
        for raw_line in markdown.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                self.output_text.insert(tk.END, raw_line + "\n", ("code_block",))
                continue
            heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading:
                tag = f"h{len(heading.group(1))}"
                self.insert_inline_markdown(heading.group(2), tag)
                self.output_text.insert(tk.END, "\n", (tag,))
                continue
            if re.fullmatch(r"([-*_])\1{2,}", stripped):
                self.output_text.insert(tk.END, "─" * 48 + "\n", ("rule",))
                continue
            if stripped.startswith(">"):
                self.insert_inline_markdown(stripped.lstrip("> "), "quote")
                self.output_text.insert(tk.END, "\n", ("quote",))
                continue
            list_item = re.match(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$", raw_line)
            if list_item:
                prefix_match = re.match(r"^\s*(\d+\.)", raw_line)
                prefix = f"{prefix_match.group(1)} " if prefix_match else "• "
                self.output_text.insert(tk.END, prefix, ("bullet",))
                self.insert_inline_markdown(list_item.group(1), "bullet")
                self.output_text.insert(tk.END, "\n", ("bullet",))
                continue
            self.insert_inline_markdown(raw_line)
            self.output_text.insert(tk.END, "\n")

    def render_preview(self) -> None:
        if not self.latest_response:
            return
        report = self.latest_response.report
        is_markdown = self.latest_response.download_name.lower().endswith(".md")
        reading = self.preview_mode_var.get() == "reading" and is_markdown
        self.output_text.configure(state="normal", fg=TEXT)
        self.output_text.delete("1.0", tk.END)
        if reading:
            self.render_markdown(report)
        else:
            self.output_text.insert("1.0", report)
        self.output_text.configure(state="disabled")

    def update_preview_mode(self) -> None:
        if self.latest_response and not self.latest_response.download_name.lower().endswith(".md"):
            self.preview_mode_var.set("source")
            self.reading_button.configure(state="disabled")
        else:
            self.reading_button.configure(state="normal")
            self._markdown_preview_mode = self.preview_mode_var.get()
        self.render_preview()

    def show_ignored_lines(self) -> None:
        if not self.latest_response or not self.latest_response.ignored_line_samples:
            return
        dialog = tk.Toplevel(self)
        dialog.title("未识别行")
        dialog.configure(bg=PANEL)
        dialog.geometry(self.geometry_px(620, 420))
        dialog.transient(self.master)
        dialog.grab_set()
        ttk.Label(
            dialog,
            text=f"以下为最多 20 条未识别的开头行，共 {self.latest_response.ignored_lines} 行。",
            style="Panel.TLabel",
        ).pack(anchor="w", padx=self.px(18), pady=(self.px(16), self.px(10)))
        text = tk.Text(
            dialog,
            wrap="word",
            bg="#ffffff",
            fg=TEXT,
            relief="flat",
            bd=0,
            padx=self.px(14),
            pady=self.px(12),
            font=(FONT_FAMILY, 9),
        )
        text.pack(fill="both", expand=True, padx=self.px(18), pady=(0, self.px(12)))
        for line_no, value in self.latest_response.ignored_line_samples:
            text.insert(tk.END, f"第 {line_no} 行\n{value}\n\n")
        text.configure(state="disabled")
        LinearButton(dialog, "关闭", dialog.destroy).pack(anchor="e", padx=self.px(18), pady=(0, self.px(16)))

    def update_status_indicator(self) -> None:
        if not hasattr(self, "status_dot"):
            return
        status = self.status_var.get()
        color = SUBTLE
        if "失败" in status or "错误" in status:
            color = "#dc2626"
        elif status.startswith("正在"):
            color = ACCENT
        elif any(token in status for token in ("已生成", "已读取", "可用", "已复制", "已导出", "连接成功")):
            color = "#16a34a"
        self.status_dot.delete("all")
        size = self.px(7)
        self.status_dot.create_oval(0, 0, size, size, fill=color, outline=color)

    def apply_date_preset(self, days: int) -> None:
        if days <= 0:
            self.date_from_var.set("")
            self.date_to_var.set("")
            return
        today = dt.date.today()
        self.date_from_var.set((today - dt.timedelta(days=days - 1)).isoformat())
        self.date_to_var.set(today.isoformat())

    def toggle_api_key_visibility(self) -> None:
        self._api_key_visible = not self._api_key_visible
        self.deepseek_key_field.set_masked(not self._api_key_visible)
        self.key_visibility_button.configure(text="隐藏" if self._api_key_visible else "显示")

    def test_deepseek_connection(self) -> None:
        api_key = self.deepseek_key_var.get().strip()
        base_url = self.deepseek_base_url_var.get().strip() or summarizer.DEFAULT_DEEPSEEK_BASE_URL

        def worker() -> str:
            return summarizer.test_deepseek_connection(api_key, base_url, timeout=15)

        self.run_background("正在测试 DeepSeek 连接...", worker, self.apply_connection_test)

    def apply_connection_test(self, result: object) -> None:
        if isinstance(result, str) and result.strip():
            self.status_var.set("DeepSeek 连接成功。")

    def add_labeled_entry(
        self,
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        *,
        columnspan: int = 1,
        show: str | None = None,
    ) -> LinearField:
        frame = ttk.Frame(parent, style="Sidebar.TFrame")
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="ew", pady=(self.px(5), 0), padx=(0 if column == 0 else self.px(8), 0))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=label, style="FieldLabel.TLabel", width=9).grid(row=0, column=0, sticky="w", padx=(0, self.px(8)))
        field = self.track(LinearField(frame, variable, show=show))
        field.grid(row=0, column=1, sticky="ew")
        return field

    def add_labeled_combo(
        self,
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        row: int,
        column: int,
        *,
        command: Callable[[object], None] | None = None,
    ) -> None:
        frame = ttk.Frame(parent, style="Sidebar.TFrame")
        frame.grid(row=row, column=column, sticky="ew", pady=(self.px(5), 0), padx=(0 if column == 0 else self.px(8), 0))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=label, style="FieldLabel.TLabel", width=9).grid(row=0, column=0, sticky="w", padx=(0, self.px(8)))
        combo = self.track(LinearSelect(frame, variable, values, command=command))
        combo.grid(row=0, column=1, sticky="ew")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择聊天记录",
            filetypes=(("文本文件", "*.txt *.csv *.log *.md"), ("所有文件", "*.*")),
        )
        if path:
            self.file_path_var.set(path)
            self.workspace_title_var.set(Path(path).name)
            self.workspace_subtitle_var.set("已选择文本文件，生成后会在下方显示摘要。")
            self.reset_generate_label()

    def update_source_mode(self) -> None:
        for button in self._source_buttons:
            selected = str(button.cget("value")) == self.source_var.get()
            button.configure(
                bg=ACCENT_SOFT if selected else "#ffffff",
                fg=ACCENT_DARK if selected else TEXT,
                highlightthickness=1,
                highlightbackground=ACCENT if selected else LINE,
            )
        if self.source_var.get() == "wechat":
            self.file_frame.grid_remove()
            self.wechat_frame.grid()
            self.summarize_button.configure(text="导出并生成摘要")
            self.workspace_title_var.set("准备导出微信会话")
            self.workspace_subtitle_var.set("刷新并选择会话后，可以直接导出聊天内容并生成摘要。")
        else:
            self.wechat_frame.grid_remove()
            self.file_frame.grid()
            self.summarize_button.configure(text="生成摘要")
            if self.file_path_var.get():
                self.workspace_title_var.set(Path(self.file_path_var.get()).name)
                self.workspace_subtitle_var.set("已选择文本文件，生成后会在下方显示摘要。")
            else:
                self.workspace_title_var.set("准备生成摘要")
                self.workspace_subtitle_var.set("选择聊天记录后，摘要会显示在这里。")
        self.reset_generate_label()

    def reset_generate_label(self) -> None:
        self.summarize_button.configure(
            text="导出并生成摘要" if self.source_var.get() == "wechat" else "生成摘要"
        )

    def on_session_selected(self) -> None:
        selected = self.wechat_session_var.get()
        if selected:
            self.workspace_title_var.set(selected)
            self.workspace_subtitle_var.set("已选择微信会话，生成后会在下方显示摘要。")
        self.reset_generate_label()

    def update_engine_mode(self) -> None:
        if self.engine_var.get() == "deepseek":
            self.deepseek_frame.grid()
            self.format_var.set("markdown")
        else:
            self.deepseek_frame.grid_remove()

    def toggle_advanced(self) -> None:
        self.advanced_expanded_var.set(not self.advanced_expanded_var.get())
        self.update_advanced_mode()

    def update_advanced_mode(self) -> None:
        if self.advanced_expanded_var.get():
            self.advanced_frame.grid()
            self.advanced_button.configure(text="高级设置  v")
        else:
            self.advanced_frame.grid_remove()
            self.advanced_button.configure(text="高级设置  >")

    def bind_settings_traces(self) -> None:
        variables: tuple[tk.Variable, ...] = (
            self.source_var,
            self.date_from_var,
            self.date_to_var,
            self.speakers_var,
            self.encoding_var,
            self.top_messages_var,
            self.engine_var,
            self.format_var,
            self.deepseek_key_var,
            self.deepseek_base_url_var,
            self.deepseek_thinking_var,
            self.deepseek_effort_var,
            self.max_input_chars_var,
            self.wechat_limit_var,
            self.wechat_session_limit_var,
            self.advanced_expanded_var,
            self.preview_mode_var,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_: self.schedule_settings_save())

    def current_settings(self) -> app_settings.AppSettings:
        return app_settings.AppSettings(
            source=self.source_var.get(),
            date_from=self.date_from_var.get(),
            date_to=self.date_to_var.get(),
            speakers=self.speakers_var.get(),
            encoding=self.encoding_var.get(),
            top_messages=self.top_messages_var.get(),
            engine=self.engine_var.get(),
            output_format=self.format_var.get(),
            deepseek_api_key=self.deepseek_key_var.get(),
            deepseek_base_url=self.deepseek_base_url_var.get(),
            deepseek_thinking=self.deepseek_thinking_var.get(),
            deepseek_effort=self.deepseek_effort_var.get(),
            max_input_chars=self.max_input_chars_var.get(),
            wechat_limit=self.wechat_limit_var.get(),
            wechat_session_limit=self.wechat_session_limit_var.get(),
            advanced_expanded=self.advanced_expanded_var.get(),
            preview_mode=self._markdown_preview_mode,
        )

    def schedule_settings_save(self) -> None:
        if not self._settings_ready or self._closing:
            return
        if self._settings_after_id is not None:
            self.after_cancel(self._settings_after_id)
        self.save_status_var.set("正在保存设置...")
        self._settings_after_id = self.after(400, self.save_settings_now)

    def save_settings_now(self) -> bool:
        self._settings_after_id = None
        try:
            self.settings_store.save(self.current_settings())
        except Exception:
            self.save_status_var.set("设置保存失败")
            return False
        self.save_status_var.set("设置已保存")
        if self._save_status_after_id is not None:
            self.after_cancel(self._save_status_after_id)
        self._save_status_after_id = self.after(2000, lambda: self.save_status_var.set(""))
        return True

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._settings_after_id is not None:
            self.after_cancel(self._settings_after_id)
            self._settings_after_id = None
        if self._save_status_after_id is not None:
            self.after_cancel(self._save_status_after_id)
            self._save_status_after_id = None
        self.save_settings_now()
        self.master.destroy()

    def destroy(self) -> None:
        self._closing = True
        if self._settings_after_id is not None:
            try:
                self.after_cancel(self._settings_after_id)
            except tk.TclError:
                pass
            self._settings_after_id = None
        if self._save_status_after_id is not None:
            try:
                self.after_cancel(self._save_status_after_id)
            except tk.TclError:
                pass
            self._save_status_after_id = None
        super().destroy()

    def sync_date_bounds(self, changed: str) -> None:
        if self._syncing_dates:
            return
        start_value = self.date_from_var.get()
        end_value = self.date_to_var.get()
        if not start_value or not end_value:
            return
        try:
            start = dt.datetime.strptime(start_value, "%Y-%m-%d").date()
            end = dt.datetime.strptime(end_value, "%Y-%m-%d").date()
        except ValueError:
            return
        if start <= end:
            return
        self._syncing_dates = True
        try:
            if changed == "from":
                self.date_to_var.set(start_value)
            else:
                self.date_from_var.set(end_value)
        finally:
            self._syncing_dates = False

    def build_summary_request(self) -> service.SummaryRequest:
        self.validate_date_order()
        return service.SummaryRequest(
            source=self.source_var.get(),
            encoding=self.encoding_var.get(),
            output_format=self.format_var.get(),
            date_from=self.date_from_var.get() or None,
            date_to=self.date_to_var.get() or None,
            speakers=service.parse_speakers(self.speakers_var.get()),
            top_messages=self.parse_int(self.top_messages_var.get(), "每类摘录数量"),
            engine=self.engine_var.get(),
            deepseek_api_key=self.deepseek_key_var.get().strip() or None,
            deepseek_base_url=self.deepseek_base_url_var.get().strip() or summarizer.DEFAULT_DEEPSEEK_BASE_URL,
            deepseek_thinking=self.deepseek_thinking_var.get(),
            deepseek_reasoning_effort=self.deepseek_effort_var.get(),
            max_input_chars=self.parse_int(self.max_input_chars_var.get(), "发送上限"),
        )

    def validate_date_order(self) -> None:
        if not self.date_from_var.get() or not self.date_to_var.get():
            return
        start = summarizer.parse_date_filter(self.date_from_var.get())
        end = summarizer.parse_date_filter(self.date_to_var.get(), end_of_day=True)
        if start and end and start > end:
            raise ValueError("起始日期不能晚于结束日期。")

    def parse_int(self, value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{label}必须是整数。") from exc

    def summarize(self) -> None:
        try:
            request = self.build_summary_request()
            if self.source_var.get() == "wechat":
                session = self.selected_wechat_session()
                limit = self.parse_int(self.wechat_limit_var.get(), "导出条数")

                def worker() -> service.SummaryResponse:
                    return service.summarize_wechat(session.name, limit, request)

                self.run_background("正在导出微信会话并生成摘要...", worker, self.apply_response)
            else:
                if not self.file_path_var.get():
                    raise ValueError("请先选择聊天记录文件。")
                path = Path(self.file_path_var.get())

                def worker() -> service.SummaryResponse:
                    return service.summarize_file(path, request)

                self.run_background("正在解析文件并生成摘要...", worker, self.apply_response)
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))

    def selected_wechat_session(self) -> wechat_cli_bridge.WechatSession:
        selected = self.wechat_session_var.get()
        for session in self.wechat_sessions:
            label = self.session_label(session)
            if selected == label:
                return session
        raise ValueError("请先刷新并选择微信会话。")

    def check_wechat_status(self) -> None:
        self.run_background("正在检测 wechat-cli...", wechat_cli_bridge.get_status, self.apply_wechat_status)

    def load_wechat_sessions(self) -> None:
        limit = self.parse_int(self.wechat_session_limit_var.get(), "会话数量")

        def worker() -> list[wechat_cli_bridge.WechatSession]:
            return wechat_cli_bridge.list_sessions(limit=limit, exclude_service=True, include_counts=True)

        self.run_background("正在读取会话列表...", worker, self.apply_wechat_sessions)

    def apply_wechat_status(self, result: object) -> None:
        status = result
        if not isinstance(status, wechat_cli_bridge.WechatCliStatus):
            return
        if status.available:
            self.status_var.set(f"wechat-cli 可用：{status.executable}")
            return
        self.status_var.set("未检测到 wechat-cli。")
        messagebox.showwarning("微信会话功能需要额外安装", status.message)

    def show_about(self) -> None:
        messagebox.showinfo(
            f"关于 {APP_NAME}",
            (
                f"{APP_NAME}\n"
                f"{APP_NAME_EN} {APP_VERSION}\n\n"
                "个人工具试用版，仅支持 64 位 Windows 10/11。\n"
                "本版本未进行 Authenticode 代码签名。\n\n"
                f"设置目录：\n{self.settings_store.path.parent}\n\n"
                "DeepSeek 模式会将筛选后的聊天内容发送到配置的 API；\n"
                "local 模式只在本机处理。"
            ),
        )

    def apply_wechat_sessions(self, result: object) -> None:
        self.wechat_sessions = list(result) if isinstance(result, list) else []
        labels = [self.session_label(session) for session in self.wechat_sessions]
        search_texts = {
            self.session_label(session): " ".join(
                (
                    self.session_label(session),
                    session.name,
                    session.display_name,
                    str(session.message_count or ""),
                )
            )
            for session in self.wechat_sessions
        }
        self.wechat_combo.configure(values=labels, search_texts=search_texts)
        self.wechat_session_var.set(labels[0] if labels else "")
        if labels:
            self.on_session_selected()
        self.status_var.set(f"已读取 {len(labels)} 个微信会话。")

    def session_label(self, session: wechat_cli_bridge.WechatSession) -> str:
        label = session.display_name or session.name
        if isinstance(session.message_count, int):
            return f"{label}（{session.message_count} 条）"
        return label

    def run_background(
        self,
        status: str,
        worker: Callable[[], object],
        callback: TaskCallback | None,
    ) -> None:
        self.status_var.set(status)
        self.set_busy_state(True)

        def target() -> None:
            try:
                result = worker()
            except Exception as exc:
                self.task_queue.put(("error", exc, None))
            else:
                self.task_queue.put(("ok", result, callback))

        threading.Thread(target=target, daemon=True).start()
        self.after(100, self.drain_tasks)

    def drain_tasks(self) -> None:
        try:
            kind, payload, callback = self.task_queue.get_nowait()
        except queue.Empty:
            self.after(100, self.drain_tasks)
            return

        self.set_busy_state(False)
        if kind == "error":
            self.status_var.set("操作失败。")
            messagebox.showerror("操作失败", str(payload))
            return
        if callback:
            callback(payload)

    def set_busy_state(self, busy: bool) -> None:
        if busy:
            widgets = self.stateful_widgets()
            previous_states: dict[tk.Widget, str] = {}
            for widget in widgets:
                try:
                    previous_states[widget] = str(widget.cget("state"))
                except tk.TclError:
                    continue
            self._busy_previous_states = previous_states
            for widget in widgets:
                try:
                    widget.configure(state="disabled")
                except tk.TclError:
                    continue
            return
        for widget, state in self._busy_previous_states.items():
            try:
                widget.configure(state=state)
            except tk.TclError:
                continue
        self._busy_previous_states.clear()
        self.set_result_actions_enabled(self.latest_response is not None)

    def stateful_widgets(self) -> list[tk.Widget]:
        widgets: list[tk.Widget] = []
        seen: set[str] = set()

        def visit(widget: tk.Widget) -> None:
            if str(widget) in seen:
                return
            seen.add(str(widget))
            try:
                widget.cget("state")
            except tk.TclError:
                pass
            else:
                if widget is not self.output_text:
                    widgets.append(widget)
            for child in widget.winfo_children():
                visit(child)

        visit(self)
        return widgets

    def set_result_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.copy_button.configure(state=state)
        self.export_button.configure(state=state)

    def current_report_text(self) -> str:
        return self.latest_response.report if self.latest_response else ""

    def apply_response(self, result: object) -> None:
        if not isinstance(result, service.SummaryResponse):
            return
        self.latest_response = result
        self.set_result_actions_enabled(True)
        self.message_count_var.set(str(result.message_count))
        self.speaker_count_var.set(str(result.speaker_count))
        self.encoding_used_var.set(result.encoding)
        self.ignored_lines_var.set(str(result.ignored_lines))
        self.meta_var.set(self.status_meta_text())
        self.ignored_button.configure(
            text=f"未识别 {result.ignored_lines}",
            state="normal" if result.ignored_line_samples else "disabled",
            fg="#b45309" if result.ignored_lines else MUTED,
        )
        if result.wechat_chat:
            self.workspace_title_var.set(result.wechat_chat)
            self.workspace_subtitle_var.set(f"来自微信会话，导出字符 {result.wechat_exported_chars}。")
        else:
            title = Path(self.file_path_var.get()).name if self.file_path_var.get() else result.download_name
            self.workspace_title_var.set(title)
            self.workspace_subtitle_var.set(f"摘要已生成，可复制或导出为 {result.download_name}。")
        if not result.download_name.lower().endswith(".md"):
            self.preview_mode_var.set("source")
        else:
            self.preview_mode_var.set(self._markdown_preview_mode)
        self.update_preview_mode()
        self.summarize_button.configure(text="重新生成")
        self.status_var.set(f"摘要已生成：{result.download_name}")

    def copy_report(self) -> None:
        if not self.latest_response:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_report_text())
        self.status_var.set("已复制到剪贴板。")

    def export_report(self) -> None:
        if not self.latest_response:
            return
        filename = self.latest_response.download_name
        path = filedialog.asksaveasfilename(
            title="导出摘要",
            initialfile=filename,
            defaultextension=Path(filename).suffix,
            filetypes=(("Markdown", "*.md"), ("JSON", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")),
        )
        if not path:
            return
        Path(path).write_text(self.current_report_text(), encoding="utf-8")
        self.status_var.set(f"已导出：{path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the desktop WeChat chat summarizer.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME_EN} {APP_VERSION}")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    parse_args(argv)
    enable_windows_dpi_awareness()
    root = tk.Tk()
    root.title(APP_NAME)
    icon_path = resource_path("assets/WeChatChatSummarizer.ico")
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass
    app = DesktopApp(root)
    root.geometry(app.geometry_px(1280, 900))
    root.minsize(1080, 820)
    root.mainloop()
    return 0
