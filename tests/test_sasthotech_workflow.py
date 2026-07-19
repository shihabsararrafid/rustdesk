import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".github/workflows/flutter-build.yml"
NIGHTLY = ROOT / ".github/workflows/flutter-nightly.yml"
TAG = ROOT / ".github/workflows/flutter-tag.yml"
WRAPPER = ROOT / ".github/workflows/sasthotech-desktop.yml"

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_yaml(path: Path):
    if not HAS_YAML:
        raise unittest.SkipTest("PyYAML not installed")
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    # PyYAML parses bare `on:` as boolean True (GitHub Actions quirk).
    if "on" not in doc and True in doc:
        doc["on"] = doc[True]
    return doc


# Matrix objects from base commit 3b552714 (hardcoded before Task 3).
EXPECTED_WINDOWS_MATRIX = [
    {
        "target": "x86_64-pc-windows-msvc",
        "os": "windows-2022",
        "arch": "x86_64",
        "flutter-arch": "x64",
        "vcpkg-triplet": "x64-windows-static",
        "build-args": "--vram",
    },
    {
        "target": "aarch64-pc-windows-msvc",
        "os": "windows-11-arm",
        "arch": "aarch64",
        "flutter-arch": "arm64",
        "vcpkg-triplet": "arm64-windows-static",
        "build-args": "",
    },
]

EXPECTED_WINDOWS_HELPER_MATRIX = [
    {"target": "windows-2022", "platform": "x64"},
    {"target": "windows-11-arm", "platform": "ARM64"},
]

EXPECTED_MACOS_MATRIX = [
    {
        "target": "x86_64-apple-darwin",
        "os": "macos-15-intel",
        "extra-build-args": "",
        "arch": "x86_64",
        "vcpkg-triplet": "x64-osx",
    },
    {
        "target": "aarch64-apple-darwin",
        "os": "macos-14",
        "extra-build-args": "--screencapturekit",
        "arch": "aarch64",
        "vcpkg-triplet": "arm64-osx",
    },
]

EXPECTED_LINUX_MATRIX = [
    {
        "arch": "x86_64",
        "target": "x86_64-unknown-linux-gnu",
        "distro": "ubuntu18.04",
        "on": "ubuntu-22.04",
        "deb_arch": "amd64",
        "vcpkg-triplet": "x64-linux",
    },
    {
        "arch": "aarch64",
        "target": "aarch64-unknown-linux-gnu",
        "distro": "ubuntu18.04",
        "on": "ubuntu-22.04-arm",
        "deb_arch": "arm64",
        "vcpkg-triplet": "arm64-linux",
    },
]

PROFILE_EXCLUDED_JOBS = [
    "build-rustdesk-ios",
    "build-for-windows-sciter",
    "build-rustdesk-android",
    "build-rustdesk-android-universal",
    "build-rustdesk-linux-sciter",
    "build-appimage",
    "build-flatpak",
    "build-rustdesk-web",
    "publish_unsigned",
]


class ReusableWorkflowTests(unittest.TestCase):
    def test_reusable_workflow_has_desktop_profile(self):
        text = BUILD.read_text()
        self.assertIn("build-profile:", text)
        self.assertIn("windows-matrix:", text)
        self.assertIn("windows-helper-matrix:", text)
        self.assertIn("macos-matrix:", text)
        self.assertIn("linux-matrix:", text)
        self.assertIn("fromJSON(inputs.windows-matrix)", text)
        self.assertIn("fromJSON(inputs.windows-helper-matrix)", text)
        self.assertIn("fromJSON(inputs.macos-matrix)", text)
        self.assertIn("fromJSON(inputs.linux-matrix)", text)

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_matrix_input_defaults_match_full_build(self):
        doc = load_yaml(BUILD)
        inputs = doc["on"]["workflow_call"]["inputs"]
        self.assertEqual(inputs["build-profile"]["default"], "full")
        self.assertEqual(
            json.loads(inputs["windows-matrix"]["default"]), EXPECTED_WINDOWS_MATRIX
        )
        self.assertEqual(
            json.loads(inputs["windows-helper-matrix"]["default"]),
            EXPECTED_WINDOWS_HELPER_MATRIX,
        )
        self.assertEqual(
            json.loads(inputs["macos-matrix"]["default"]), EXPECTED_MACOS_MATRIX
        )
        self.assertEqual(
            json.loads(inputs["linux-matrix"]["default"]), EXPECTED_LINUX_MATRIX
        )

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_selectable_jobs_use_fromjson_inputs(self):
        doc = load_yaml(BUILD)
        jobs = doc["jobs"]
        self.assertEqual(
            jobs["build-for-windows-flutter"]["strategy"]["matrix"]["job"],
            "${{ fromJSON(inputs.windows-matrix) }}",
        )
        self.assertEqual(
            jobs["build-RustDeskTempTopMostWindow"]["strategy"]["matrix"]["job"],
            "${{ fromJSON(inputs.windows-helper-matrix) }}",
        )
        self.assertEqual(
            jobs["build-for-macOS"]["strategy"]["matrix"]["job"],
            "${{ fromJSON(inputs.macos-matrix) }}",
        )
        self.assertEqual(
            jobs["build-rustdesk-linux"]["strategy"]["matrix"]["job"],
            "${{ fromJSON(inputs.linux-matrix) }}",
        )

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_sasthotech_profile_excludes_non_desktop_jobs(self):
        doc = load_yaml(BUILD)
        jobs = doc["jobs"]
        for job_id in PROFILE_EXCLUDED_JOBS:
            with self.subTest(job=job_id):
                job_if = jobs[job_id].get("if")
                self.assertIsNotNone(job_if, f"{job_id} missing job-level if")
                self.assertIn(
                    "inputs.build-profile != 'sasthotech-desktop'", str(job_if)
                )

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_profile_conditions_preserve_existing_upload_artifact_guards(self):
        doc = load_yaml(BUILD)
        jobs = doc["jobs"]
        upload_guard_jobs = [
            "build-rustdesk-ios",
            "build-rustdesk-android-universal",
            "build-rustdesk-linux-sciter",
            "build-appimage",
            "build-flatpak",
            "publish_unsigned",
        ]
        for job_id in upload_guard_jobs:
            with self.subTest(job=job_id):
                job_if = str(jobs[job_id]["if"])
                self.assertIn("inputs.upload-artifact", job_if)
                self.assertIn("&&", job_if)

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_nightly_and_tag_callers_rely_on_full_defaults(self):
        for path in (NIGHTLY, TAG):
            with self.subTest(caller=path.name):
                doc = load_yaml(path)
                job = next(iter(doc["jobs"].values()))
                with_block = job.get("with", {})
                for key in (
                    "build-profile",
                    "windows-matrix",
                    "windows-helper-matrix",
                    "macos-matrix",
                    "linux-matrix",
                ):
                    self.assertNotIn(
                        key,
                        with_block,
                        f"{path.name} must omit {key} to keep full-build defaults",
                    )


class WrapperWorkflowTests(unittest.TestCase):
    """Task 4 adds sasthotech-desktop.yml and enables these tests."""

    @unittest.skipUnless(WRAPPER.exists(), "Task 4 wrapper not yet created")
    def test_manual_wrapper_selects_only_confirmed_targets(self):
        text = WRAPPER.read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("x86_64-pc-windows-msvc", text)
        self.assertIn("x86_64-unknown-linux-gnu", text)
        self.assertIn("x86_64-apple-darwin", text)
        self.assertIn("aarch64-apple-darwin", text)
        self.assertNotIn("android", text.lower())
        self.assertNotIn("ios", text.lower())


class TextFallbackTests(unittest.TestCase):
    """Minimal assertions when PyYAML is unavailable."""

    def test_build_profile_default_is_full(self):
        text = BUILD.read_text()
        self.assertRegex(
            text,
            re.compile(
                r"build-profile:\s*\n\s*type:\s*string\s*\n\s*default:\s*\"full\"",
                re.MULTILINE,
            ),
        )

    def test_nightly_tag_do_not_override_matrix_inputs(self):
        for path in (NIGHTLY, TAG):
            text = path.read_text()
            self.assertNotIn("build-profile:", text)
            self.assertNotIn("windows-matrix:", text)
            self.assertNotIn("macos-matrix:", text)
            self.assertNotIn("linux-matrix:", text)


if __name__ == "__main__":
    unittest.main()
