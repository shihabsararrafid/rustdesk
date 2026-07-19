import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "Sasthotech Remote.app"


def _strip_quoted_strings(line: str) -> str:
    stripped = line
    for quoted in re.findall(r'"[^"]*"', line):
        stripped = stripped.replace(quoted, '""')
    for quoted in re.findall(r"'[^']*'", line):
        stripped = stripped.replace(quoted, "''")
    return stripped


class BrandingTests(unittest.TestCase):
    def test_macos_bundle_name_is_consistent(self):
        config = (ROOT / "flutter/macos/Runner/Configs/AppInfo.xcconfig").read_text()
        build = (ROOT / "build.py").read_text()
        workflow = (ROOT / ".github/workflows/flutter-build.yml").read_text()
        self.assertIn("PRODUCT_NAME = Sasthotech Remote", config)
        self.assertIn(f'MACOS_APP_BUNDLE = "{BUNDLE}"', build)
        self.assertIn(BUNDLE, workflow)
        self.assertIn("sasthotech-remote-", workflow)
        self.assertIn("sasthotech-remote-${{ env.VERSION }}-unsigned.tar.gz", workflow)

    def test_macos_shell_paths_quote_bundle_name(self):
        build = (ROOT / "build.py").read_text()
        workflow = (ROOT / ".github/workflows/flutter-build.yml").read_text()

        self.assertIn('"{app_path}/Contents/MacOS/"', build)

        for i, line in enumerate(workflow.splitlines(), 1):
            if BUNDLE not in line:
                continue
            if BUNDLE in _strip_quoted_strings(line):
                self.fail(
                    "unquoted bundle path in workflow line "
                    f"{i}: {line.strip()}"
                )

    def test_linux_visible_name_is_branded(self):
        for name in ("rustdesk.desktop", "rustdesk-link.desktop"):
            text = (ROOT / "res" / name).read_text()
            self.assertIn("Name=Sasthotech Remote", text)
