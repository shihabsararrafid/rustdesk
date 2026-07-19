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

    def test_windows_visible_branding_preserves_internal_exe(self):
        runner = (ROOT / "flutter/windows/runner/Runner.rc").read_text()
        portable = (ROOT / "libs/portable/Cargo.toml").read_text()
        workflow = (ROOT / ".github/workflows/flutter-build.yml").read_text()
        preprocess = (ROOT / "res/msi/preprocess.py").read_text()

        self.assertIn('VALUE "ProductName", "Sasthotech Remote"', runner)
        self.assertIn('VALUE "FileDescription", "Sasthotech Remote"', runner)
        self.assertIn('VALUE "InternalName", "rustdesk"', runner)
        self.assertIn('VALUE "OriginalFilename", "rustdesk.exe"', runner)

        self.assertIn('ProductName = "Sasthotech Remote"', portable)
        self.assertIn('FileDescription = "Sasthotech Remote"', portable)
        self.assertIn('OriginalFilename = "rustdesk.exe"', portable)

        self.assertIn('--display-name "Sasthotech Remote"', workflow)
        self.assertIn("--app-name rustdesk", workflow)
        self.assertIn("--display-name", preprocess)
        self.assertIn("display_name", preprocess)
