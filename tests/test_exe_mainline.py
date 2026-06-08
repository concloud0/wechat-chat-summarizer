import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExeMainlineTests(unittest.TestCase):
    def test_web_mode_source_files_are_removed(self):
        self.assertFalse((ROOT / "wxchat_webapp.py").exists())
        self.assertFalse((ROOT / "wxchat_app" / "webapp.py").exists())
        self.assertFalse((ROOT / "web").exists())
        self.assertFalse((ROOT / "web" / "index.html").exists())

    def test_portable_packaging_clears_only_resolved_package_directory(self):
        script = (ROOT / "package_portable.ps1").read_text(encoding="utf-8")

        self.assertIn("[System.IO.Path]::GetFullPath((Join-Path $root \"dist\"))", script)
        self.assertIn("[System.IO.Path]::GetFullPath((Join-Path $dist \"WeChatChatSummarizerPortable\"))", script)
        self.assertIn("$package.StartsWith($dist, [System.StringComparison]::OrdinalIgnoreCase)", script)
        self.assertIn("Remove-Item -LiteralPath $package -Recurse -Force", script)
        self.assertNotIn("wxchat_webapp.py", script)
        self.assertNotIn("web\\index.html", script)


if __name__ == "__main__":
    unittest.main()
