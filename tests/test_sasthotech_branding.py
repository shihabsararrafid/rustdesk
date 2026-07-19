import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_macos_bundle_name_is_consistent(self):
        config = (ROOT / "flutter/macos/Runner/Configs/AppInfo.xcconfig").read_text()
        build = (ROOT / "build.py").read_text()
        workflow = (ROOT / ".github/workflows/flutter-build.yml").read_text()
        self.assertIn("PRODUCT_NAME = Sasthotech Remote", config)
        self.assertIn('MACOS_APP_BUNDLE = "Sasthotech Remote.app"', build)
        self.assertIn("Sasthotech Remote.app", workflow)
        self.assertIn("sasthotech-remote-", workflow)

    def test_linux_visible_name_is_branded(self):
        for name in ("rustdesk.desktop", "rustdesk-link.desktop"):
            text = (ROOT / "res" / name).read_text()
            self.assertIn("Name=Sasthotech Remote", text)
