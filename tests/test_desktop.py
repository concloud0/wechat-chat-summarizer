import tempfile
import unittest
import datetime as dt
from pathlib import Path
from unittest import mock

from wxchat_app import service
from wxchat_app import wechat_cli_bridge
from wxchat_app.version import APP_VERSION


class FakeProtector:
    def protect(self, value):
        return f"protected:{value[::-1]}"

    def unprotect(self, value):
        if not value.startswith("protected:"):
            raise ValueError("invalid")
        return value.removeprefix("protected:")[::-1]


class DesktopTests(unittest.TestCase):
    def make_app(self, config_path=None):
        try:
            import tkinter as tk
            from wxchat_app.desktop import DesktopApp
        except Exception as exc:
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"no GUI display: {exc}")

        temporary = None
        if config_path is None:
            temporary = tempfile.TemporaryDirectory()
            config_path = Path(temporary.name) / "settings.json"
        app = DesktopApp(root, config_path=Path(config_path), secret_protector=FakeProtector())
        root._settings_temporary = temporary
        root.update_idletasks()
        return root, app

    def widget_classes(self, widget):
        classes = []

        def walk(current):
            classes.append(current.winfo_class())
            for child in current.winfo_children():
                walk(child)

        walk(widget)
        return classes

    def test_desktop_request_builder(self):
        root, app = self.make_app()
        try:
            app.engine_var.set("deepseek")
            app.date_from_var.set("2026-06-01")
            app.date_to_var.set("2026-06-03")
            app.speakers_var.set("张三, 李四")
            app.deepseek_key_var.set("test-api-key")

            request = app.build_summary_request()
        finally:
            root.destroy()

        self.assertIsInstance(request, service.SummaryRequest)
        self.assertEqual(request.engine, "deepseek")
        self.assertEqual(request.speakers, ("张三", "李四"))
        self.assertEqual(request.deepseek_api_key, "test-api-key")

    def test_defaults_to_deepseek_markdown_with_advanced_collapsed(self):
        root, app = self.make_app()
        try:
            self.assertEqual(app.engine_var.get(), "deepseek")
            self.assertEqual(app.format_var.get(), "markdown")
            self.assertFalse(app.advanced_expanded_var.get())
            self.assertFalse(app.advanced_frame.grid_info())
        finally:
            root.destroy()

    def test_about_dialog_contains_version_and_unsigned_notice(self):
        root, app = self.make_app()
        try:
            with mock.patch("wxchat_app.desktop.messagebox.showinfo") as showinfo:
                app.show_about()
            text = showinfo.call_args.args[1]
            self.assertIn(APP_VERSION, text)
            self.assertIn("未进行 Authenticode", text)
            self.assertIn(str(app.settings_store.path.parent), text)
        finally:
            root.destroy()

    def test_source_toggle_updates_visible_panel(self):
        root, app = self.make_app()
        try:
            app.source_var.set("wechat")
            app.update_source_mode()
            root.update_idletasks()

            self.assertFalse(app.file_frame.grid_info())
            self.assertTrue(app.wechat_frame.grid_info())
            self.assertEqual(app.summarize_button.cget("text"), "导出并生成摘要")

            app.source_var.set("file")
            app.update_source_mode()
            root.update_idletasks()

            self.assertTrue(app.file_frame.grid_info())
            self.assertFalse(app.wechat_frame.grid_info())
            self.assertEqual(app.summarize_button.cget("text"), "生成摘要")
        finally:
            root.destroy()

    def test_deepseek_toggle_shows_config_and_forces_markdown(self):
        root, app = self.make_app()
        try:
            app.format_var.set("json")
            app.engine_var.set("deepseek")
            app.update_engine_mode()
            root.update_idletasks()

            self.assertTrue(app.deepseek_frame.grid_info())
            self.assertEqual(app.format_var.get(), "markdown")

            app.engine_var.set("local")
            app.update_engine_mode()
            root.update_idletasks()

            self.assertFalse(app.deepseek_frame.grid_info())
        finally:
            root.destroy()

    def test_advanced_settings_toggle(self):
        root, app = self.make_app()
        try:
            app.toggle_advanced()
            root.update_idletasks()
            self.assertTrue(app.advanced_expanded_var.get())
            self.assertTrue(app.advanced_frame.grid_info())
            self.assertEqual(app.advanced_button.cget("text"), "高级设置  v")

            app.toggle_advanced()
            root.update_idletasks()
            self.assertFalse(app.advanced_frame.grid_info())
        finally:
            root.destroy()

    def test_settings_save_and_restore_without_transient_source_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.json"
            root, app = self.make_app(config_path)
            try:
                app.source_var.set("wechat")
                app.speakers_var.set("张三")
                app.deepseek_key_var.set("test-api-key-secret")
                app.deepseek_effort_var.set("high")
                app.advanced_expanded_var.set(True)
                app.file_path_var.set("D:/private/chat.txt")
                app.wechat_session_var.set("私人会话")
                self.assertTrue(app.save_settings_now())
            finally:
                root.destroy()

            raw = config_path.read_text(encoding="utf-8")
            self.assertNotIn("test-api-key-secret", raw)
            self.assertNotIn("D:/private/chat.txt", raw)
            self.assertNotIn("私人会话", raw)

            root, restored = self.make_app(config_path)
            try:
                self.assertEqual(restored.source_var.get(), "wechat")
                self.assertEqual(restored.speakers_var.get(), "张三")
                self.assertEqual(restored.deepseek_key_var.get(), "test-api-key-secret")
                self.assertEqual(restored.deepseek_effort_var.get(), "high")
                self.assertTrue(restored.advanced_expanded_var.get())
                self.assertEqual(restored.file_path_var.get(), "")
                self.assertEqual(restored.wechat_session_var.get(), "")
            finally:
                root.destroy()

    def test_settings_auto_save_after_change(self):
        root, app = self.make_app()
        try:
            app.speakers_var.set("自动保存")
            self.assertEqual(app.save_status_var.get(), "正在保存设置...")
            root.after(450, root.quit)
            root.mainloop()
            self.assertTrue(app.settings_store.path.exists())
            self.assertEqual(app.save_status_var.get(), "设置已保存")
        finally:
            root.destroy()

    def test_settings_save_failure_is_nonfatal(self):
        root, app = self.make_app()
        try:
            def fail(_settings):
                raise OSError("disk unavailable")

            app.settings_store.save = fail
            self.assertFalse(app.save_settings_now())
            self.assertEqual(app.save_status_var.get(), "设置保存失败")
        finally:
            root.destroy()

    def test_result_actions_start_disabled_and_preview_is_readonly(self):
        root, app = self.make_app()
        try:
            self.assertEqual(str(app.copy_button.cget("state")), "disabled")
            self.assertEqual(str(app.export_button.cget("state")), "disabled")
            self.assertEqual(str(app.output_text.cget("state")), "disabled")

            response = service.SummaryResponse(
                report="## 摘要\n内容",
                download_name="summary.md",
                encoding="utf-8",
                message_count=3,
                speaker_count=2,
                ignored_lines=0,
                engine="local",
                model="local",
                thinking="off",
                reasoning_effort="",
                source="file",
            )
            app.apply_response(response)

            self.assertEqual(str(app.copy_button.cget("state")), "normal")
            self.assertEqual(str(app.export_button.cget("state")), "normal")
            self.assertEqual(str(app.output_text.cget("state")), "disabled")
            self.assertEqual(app.current_report_text(), response.report)
            self.assertEqual(app.meta_var.get(), "消息 3 · 成员 2 · 编码 utf-8 · 未识别 0")
        finally:
            root.destroy()

    def test_markdown_reading_view_and_source_switch_keep_raw_report(self):
        root, app = self.make_app()
        report = "# 标题\n\n## 小节\n\n- **重点**、`code` 和 [链接](https://example.com)\n\n> 引用\n\n```\nblock\n```\n"
        try:
            response = service.SummaryResponse(
                report=report,
                download_name="summary.md",
                encoding="utf-8",
                message_count=1,
                speaker_count=1,
                ignored_lines=0,
                engine="local",
                model="local",
                thinking="off",
                reasoning_effort="",
                source="file",
            )
            app.apply_response(response)

            reading_text = app.output_text.get("1.0", "end-1c")
            self.assertNotIn("# 标题", reading_text)
            self.assertTrue(app.output_text.tag_ranges("h1"))
            self.assertTrue(app.output_text.tag_ranges("bold"))
            self.assertTrue(app.output_text.tag_ranges("code"))
            self.assertTrue(app.output_text.tag_ranges("quote"))
            self.assertTrue(app.output_text.tag_ranges("code_block"))
            self.assertTrue(app.output_text.tag_ranges("link"))
            self.assertEqual(app.current_report_text(), report)

            app.preview_mode_var.set("source")
            app.update_preview_mode()
            self.assertEqual(app.output_text.get("1.0", "end-1c"), report)
            self.assertEqual(app.current_report_text(), report)
        finally:
            root.destroy()

    def test_json_result_forces_source_preview(self):
        root, app = self.make_app()
        try:
            app.preview_mode_var.set("reading")
            response = service.SummaryResponse(
                report='{\n  "ok": true\n}',
                download_name="summary.json",
                encoding="utf-8",
                message_count=1,
                speaker_count=1,
                ignored_lines=0,
                engine="local",
                model="local",
                thinking="off",
                reasoning_effort="",
                source="file",
            )
            app.apply_response(response)
            self.assertEqual(app.preview_mode_var.get(), "source")
            self.assertEqual(str(app.reading_button.cget("state")), "disabled")
            self.assertEqual(app.current_settings().preview_mode, "reading")

            markdown_response = service.SummaryResponse(
                report="## Markdown",
                download_name="summary.md",
                encoding="utf-8",
                message_count=1,
                speaker_count=1,
                ignored_lines=0,
                engine="local",
                model="local",
                thinking="off",
                reasoning_effort="",
                source="file",
            )
            app.apply_response(markdown_response)
            self.assertEqual(app.preview_mode_var.get(), "reading")
        finally:
            root.destroy()

    def test_ignored_line_samples_enable_diagnostic_action(self):
        root, app = self.make_app()
        try:
            response = service.SummaryResponse(
                report="## 摘要\n内容",
                download_name="summary.md",
                encoding="utf-8",
                message_count=1,
                speaker_count=1,
                ignored_lines=2,
                engine="local",
                model="local",
                thinking="off",
                reasoning_effort="",
                source="file",
                ignored_line_samples=((1, "说明"), (2, "标题")),
            )
            app.apply_response(response)
            self.assertEqual(app.ignored_button.cget("text"), "未识别 2")
            self.assertEqual(str(app.ignored_button.cget("state")), "normal")
        finally:
            root.destroy()

    def test_date_bounds_keep_valid_range(self):
        root, app = self.make_app()
        try:
            app.date_from_var.set("2026-06-10")
            app.date_to_var.set("2026-06-01")
            self.assertEqual(app.date_from_var.get(), "2026-06-01")
            self.assertEqual(app.date_to_var.get(), "2026-06-01")

            app.date_to_var.set("2026-06-15")
            app.date_from_var.set("2026-06-20")
            self.assertEqual(app.date_from_var.get(), "2026-06-20")
            self.assertEqual(app.date_to_var.get(), "2026-06-20")
        finally:
            root.destroy()

    def test_date_presets(self):
        root, app = self.make_app()
        try:
            today = dt.date.today()
            app.apply_date_preset(7)
            self.assertEqual(app.date_from_var.get(), (today - dt.timedelta(days=6)).isoformat())
            self.assertEqual(app.date_to_var.get(), today.isoformat())
            app.apply_date_preset(0)
            self.assertEqual(app.date_from_var.get(), "")
            self.assertEqual(app.date_to_var.get(), "")
        finally:
            root.destroy()

    def test_settings_panel_content_fits_panel_width(self):
        root, app = self.make_app()
        try:
            root.update_idletasks()
            self.assertLessEqual(app.settings_panel.winfo_reqwidth(), app.settings_panel.master.winfo_reqwidth())
            self.assertLessEqual(app.controls_panel.winfo_reqwidth(), app.controls_panel.master.winfo_reqwidth())
            classes = self.widget_classes(app)
            self.assertNotIn("TScrollbar", classes)
            self.assertNotIn("TCombobox", classes)
        finally:
            root.destroy()

    def test_linear_select_updates_variable(self):
        root, app = self.make_app()
        try:
            app.wechat_combo.configure(values=("会话 A", "会话 B"))
            app.wechat_combo.select_value("会话 B")
            self.assertEqual(app.wechat_session_var.get(), "会话 B")
        finally:
            root.destroy()

    def test_session_search_matches_display_internal_name_and_count(self):
        root, app = self.make_app()
        try:
            session = wechat_cli_bridge.WechatSession(
                name="internal-room-id",
                display_name="项目讨论群",
                raw={},
                message_count=85281,
            )
            app.apply_wechat_sessions([session])
            label = app.session_label(session)
            self.assertEqual(app.wechat_combo.filtered_values("项目"), [label])
            self.assertEqual(app.wechat_combo.filtered_values("internal"), [label])
            self.assertEqual(app.wechat_combo.filtered_values("85281"), [label])
            self.assertEqual(app.wechat_combo.filtered_values("missing"), [])
        finally:
            root.destroy()

    def test_api_key_visibility_and_connection_test(self):
        root, app = self.make_app()
        try:
            self.assertEqual(app.deepseek_key_field.entry.cget("show"), "*")
            app.toggle_api_key_visibility()
            self.assertEqual(app.deepseek_key_field.entry.cget("show"), "")
            self.assertEqual(app.key_visibility_button.cget("text"), "隐藏")
            app.toggle_api_key_visibility()
            self.assertEqual(app.deepseek_key_field.entry.cget("show"), "*")

            app.deepseek_key_var.set("test-api-key")
            captured = {}

            def run_background(status, worker, callback):
                captured["status"] = status
                with mock.patch(
                    "wxchat_app.summarizer.test_deepseek_connection",
                    return_value="OK\n",
                ) as api:
                    callback(worker())
                    captured["call"] = api.call_args

            app.run_background = run_background
            app.test_deepseek_connection()

            self.assertEqual(captured["status"], "正在测试 DeepSeek 连接...")
            self.assertEqual(captured["call"].args[0], "test-api-key")
            self.assertEqual(captured["call"].kwargs["timeout"], 15)
            self.assertEqual(app.status_var.get(), "DeepSeek 连接成功。")
        finally:
            root.destroy()

    def test_missing_wechat_cli_shows_install_guidance(self):
        root, app = self.make_app()
        try:
            status = wechat_cli_bridge.WechatCliStatus(
                available=False,
                executable=None,
                message=wechat_cli_bridge.WECHAT_CLI_SETUP_GUIDANCE,
            )
            with mock.patch("wxchat_app.desktop.messagebox.showwarning") as warning:
                app.apply_wechat_status(status)
            self.assertEqual(app.status_var.get(), "未检测到 wechat-cli。")
            guidance = warning.call_args.args[1]
            self.assertIn("python -m pip install", guidance)
            self.assertIn("wechat-cli init", guidance)
            self.assertIn("文本文件摘要不受影响", guidance)
        finally:
            root.destroy()

    def test_advanced_settings_and_footer_fit_default_window(self):
        root, app = self.make_app()
        try:
            root.deiconify()
            root.geometry("1280x900")
            root.update()
            app.toggle_advanced()
            root.update()
            panel_bottom = app.controls_panel.master.winfo_rooty() + app.controls_panel.master.winfo_height()
            button_bottom = app.summarize_button.winfo_rooty() + app.summarize_button.winfo_height()
            self.assertLessEqual(button_bottom, panel_bottom)
        finally:
            root.destroy()

    def test_busy_state_disables_and_restores_controls(self):
        root, app = self.make_app()
        try:
            member_field = next(
                widget
                for widget in app.stateful_widgets()
                if getattr(widget, "variable", None) is app.speakers_var
            )
            self.assertEqual(str(member_field.entry.cget("state")), "normal")
            self.assertEqual(str(app.summarize_button.cget("state")), "normal")
            app.set_busy_state(True)
            self.assertEqual(str(member_field.entry.cget("state")), "disabled")
            self.assertEqual(str(app.summarize_button.cget("state")), "disabled")
            self.assertEqual(str(app.copy_button.cget("state")), "disabled")
            app.set_busy_state(False)
            self.assertEqual(str(member_field.entry.cget("state")), "normal")
            self.assertEqual(str(app.summarize_button.cget("state")), "normal")
            self.assertEqual(str(app.copy_button.cget("state")), "disabled")
        finally:
            root.destroy()

    def test_clicking_linear_field_focuses_entry(self):
        root, app = self.make_app()
        try:
            root.deiconify()
            root.update()
            member_field = next(
                widget
                for widget in app.stateful_widgets()
                if getattr(widget, "variable", None) is app.speakers_var
            )
            member_field.event_generate("<Button-1>")
            root.update()
            self.assertIs(root.focus_get(), member_field.entry)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
