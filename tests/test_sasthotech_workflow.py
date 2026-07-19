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


SASTHOTECH_INSTALLER_UPLOADS = [
    "Upload Sasthotech Windows installers",
    "Upload Sasthotech Linux installers",
    "Upload Sasthotech macOS installer",
]

INSTALLER_UPLOAD_JOB_PAIRS = [
    (
        "build-for-windows-flutter",
        "Upload Sasthotech Windows installers",
        "Publish Release",
    ),
    (
        "build-rustdesk-linux",
        "Upload Sasthotech Linux installers",
        "Publish debian/rpm package",
    ),
    (
        "build-for-macOS",
        "Upload Sasthotech macOS installer",
        "Publish DMG package",
    ),
]

UPLOAD_STEP_TO_JOB = {
    step: job_id for job_id, step, _publish in INSTALLER_UPLOAD_JOB_PAIRS
}

MACOS_DMG_TARGET = (
    "sasthotech-remote-${{ env.VERSION }}-${{ matrix.job.arch }}.dmg"
)


def job_text_block(text: str, job_id: str) -> str:
    pattern = re.compile(
        rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-zA-Z][\w-]+:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"job not found: {job_id}")
    return match.group(0)


def job_step_names_yaml(doc, job_id: str):
    names = []
    for step in doc["jobs"][job_id].get("steps", []):
        if isinstance(step, dict) and "name" in step:
            names.append(step["name"])
    return names


def step_index_in_job_yaml(doc, job_id: str, step_name: str) -> int:
    names = job_step_names_yaml(doc, job_id)
    if step_name not in names:
        raise ValueError(f"{step_name} not in job {job_id}")
    return names.index(step_name)


def step_block_in_job(text: str, job_id: str, step_name: str) -> str:
    block = job_text_block(text, job_id)
    marker = f"- name: {step_name}"
    start = block.index(marker)
    next_step = block.find("\n      - name:", start + 1)
    if next_step == -1:
        next_step = len(block)
    return block[start:next_step]


class InstallerUploadTests(unittest.TestCase):
    def setUp(self):
        self.workflow = BUILD.read_text()
        if HAS_YAML:
            with BUILD.open() as fh:
                self.doc = yaml.safe_load(fh)
            if "on" not in self.doc and True in self.doc:
                self.doc["on"] = self.doc[True]
        else:
            self.doc = None

    def test_installer_uploads_precede_publish_steps(self):
        if HAS_YAML:
            for job_id, upload_name, publish_name in INSTALLER_UPLOAD_JOB_PAIRS:
                with self.subTest(job=job_id, mode="yaml"):
                    self.assertLess(
                        step_index_in_job_yaml(self.doc, job_id, upload_name),
                        step_index_in_job_yaml(self.doc, job_id, publish_name),
                    )
        for job_id, upload_name, publish_name in INSTALLER_UPLOAD_JOB_PAIRS:
            with self.subTest(job=job_id, mode="text"):
                block = job_text_block(self.workflow, job_id)
                self.assertLess(
                    block.index(f"- name: {upload_name}"),
                    block.index(f"- name: {publish_name}"),
                )

    def test_sasthotech_uploads_use_if_no_files_found_error(self):
        for step_name in SASTHOTECH_INSTALLER_UPLOADS:
            with self.subTest(step=step_name):
                job_id = UPLOAD_STEP_TO_JOB[step_name]
                block = step_block_in_job(self.workflow, job_id, step_name)
                self.assertIn("if-no-files-found: error", block)

    def test_windows_installer_upload_uses_signoutput_globs(self):
        block = step_block_in_job(
            self.workflow,
            "build-for-windows-flutter",
            "Upload Sasthotech Windows installers",
        )
        self.assertIn("SignOutput/*.exe", block)
        self.assertIn("SignOutput/*.msi", block)
        self.assertIn("sasthotech-remote-windows-${{ matrix.job.arch }}", block)

    def test_linux_installer_upload_includes_deb_and_rpm(self):
        job = job_text_block(self.workflow, "build-rustdesk-linux")
        rename = step_block_in_job(
            self.workflow,
            "build-rustdesk-linux",
            "Rename Sasthotech Linux installers",
        )
        upload = step_block_in_job(
            self.workflow,
            "build-rustdesk-linux",
            "Upload Sasthotech Linux installers",
        )
        publish = step_block_in_job(
            self.workflow,
            "build-rustdesk-linux",
            "Publish debian/rpm package",
        )
        self.assertIn('mv -- "$f" "sasthotech-remote-${f#rustdesk-}"', rename)
        self.assertIn("sasthotech-remote-*.deb", upload)
        self.assertIn("sasthotech-remote-*.rpm", upload)
        self.assertIn("sasthotech-remote-linux-${{ matrix.job.arch }}", upload)
        self.assertIn("sasthotech-remote-*.deb", publish)
        self.assertIn("sasthotech-remote-*.rpm", publish)
        # User-facing Flutter Linux artifact globs must not remain rustdesk-*.
        for block in (upload, publish):
            self.assertNotRegex(block, r"(?m)^\s+rustdesk-\*\.(deb|rpm)\s*$")
        self.assertIn("Rename Sasthotech Linux installers", job)
        self.assertLess(
            job.index("Rename Sasthotech Linux installers"),
            job.index("Upload Sasthotech Linux installers"),
        )

    def test_macos_installer_upload_uses_branded_dmg_path(self):
        block = step_block_in_job(
            self.workflow,
            "build-for-macOS",
            "Upload Sasthotech macOS installer",
        )
        self.assertIn(f"path: {MACOS_DMG_TARGET}", block)
        self.assertIn("sasthotech-remote-macos-${{ matrix.job.arch }}", block)

    def test_macos_dmg_rename_is_idempotent(self):
        block = step_block_in_job(
            self.workflow, "build-for-macOS", "Rename rustdesk"
        )
        self.assertIn(MACOS_DMG_TARGET, block)
        self.assertIn('[ "$name" = "$target" ]', block)
        self.assertNotIn("${name%%.dmg}-${{ matrix.job.arch }}.dmg", block)
        upload_block = step_block_in_job(
            self.workflow, "build-for-macOS", "Upload Sasthotech macOS installer"
        )
        self.assertIn(f"path: {MACOS_DMG_TARGET}", upload_block)


DESKTOP_FLUTTER_JOBS = [
    "build-for-windows-flutter",
    "build-for-macOS",
    "build-rustdesk-linux",
]

REGISTRATION_ENV_KEYS = (
    "SASTHOTECH_REGISTRATION_URL",
    "SASTHOTECH_REGISTRATION_TOKEN",
)

ARCH_LINUX_STEPS = [
    "Patch archlinux PKGBUILD",
    "Build archlinux package",
    "Publish archlinux package",
]

VALIDATION_STEP = "Validate registration webhook configuration"


class RegistrationWebhookConfigTests(unittest.TestCase):
    def setUp(self):
        self.workflow = BUILD.read_text()
        if HAS_YAML:
            self.doc = load_yaml(BUILD)
        else:
            self.doc = None

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_desktop_jobs_define_registration_secret_env(self):
        for job_id in DESKTOP_FLUTTER_JOBS:
            with self.subTest(job=job_id):
                env = self.doc["jobs"][job_id]["env"]
                for key in REGISTRATION_ENV_KEYS:
                    self.assertEqual(
                        env[key],
                        f"${{{{ secrets.{key} }}}}",
                    )

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_desktop_jobs_validate_registration_on_sasthotech_profile(self):
        for job_id in DESKTOP_FLUTTER_JOBS:
            with self.subTest(job=job_id):
                steps = self.doc["jobs"][job_id]["steps"]
                validation = next(
                    step
                    for step in steps
                    if step.get("name") == VALIDATION_STEP
                )
                self.assertEqual(
                    validation["if"], "inputs.build-profile == 'sasthotech-desktop'"
                )
                run = validation["run"]
                for key in REGISTRATION_ENV_KEYS:
                    self.assertIn(f"${key}", run)

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_linux_docker_forwards_registration_env_to_cargo_container(self):
        steps = self.doc["jobs"]["build-rustdesk-linux"]["steps"]
        build_step = next(
            step for step in steps if step.get("name") == "Build rustdesk"
        )
        docker_args = build_step["with"]["dockerRunArgs"]
        self.assertIn("--env SASTHOTECH_REGISTRATION_URL", docker_args)
        self.assertIn("--env SASTHOTECH_REGISTRATION_TOKEN", docker_args)
        self.assertNotIn("${{ secrets.", docker_args)

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_archlinux_steps_skip_sasthotech_desktop_profile(self):
        steps = self.doc["jobs"]["build-rustdesk-linux"]["steps"]
        for step_name in ARCH_LINUX_STEPS:
            with self.subTest(step=step_name):
                step = next(s for s in steps if s.get("name") == step_name)
                self.assertIn(
                    "inputs.build-profile != 'sasthotech-desktop'", step["if"]
                )

    def test_desktop_jobs_define_registration_secret_env_text(self):
        for job_id in DESKTOP_FLUTTER_JOBS:
            with self.subTest(job=job_id):
                block = job_text_block(self.workflow, job_id)
                for key in REGISTRATION_ENV_KEYS:
                    self.assertIn(f"{key}: ${{{{ secrets.{key} }}}}", block)

    def test_linux_docker_forwards_registration_env_text(self):
        block = job_text_block(self.workflow, "build-rustdesk-linux")
        docker_match = re.search(
            r"dockerRunArgs: \|\n"
            r"            --volume \"\$\{PWD\}:/workspace\"\n"
            r"            --volume \"/opt/artifacts:/opt/artifacts\"\n"
            r"            --env SASTHOTECH_REGISTRATION_URL\n"
            r"            --env SASTHOTECH_REGISTRATION_TOKEN",
            block,
        )
        self.assertIsNotNone(
            docker_match, "cargo container dockerRunArgs must forward registration env"
        )
        docker_args = docker_match.group(0)
        self.assertNotIn("${{ secrets.", docker_args)

    def test_archlinux_steps_skip_sasthotech_desktop_profile_text(self):
        for step_name in ARCH_LINUX_STEPS:
            with self.subTest(step=step_name):
                block = step_block_in_job(
                    self.workflow, "build-rustdesk-linux", step_name
                )
                self.assertIn(
                    "inputs.build-profile != 'sasthotech-desktop'", block
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

    @unittest.skipUnless(HAS_YAML and WRAPPER.exists(), "PyYAML or wrapper missing")
    def test_wrapper_calls_reusable_workflow_with_sasthotech_profile(self):
        doc = load_yaml(WRAPPER)
        self.assertEqual(doc["on"], {"workflow_dispatch": None})
        build = doc["jobs"]["build"]
        self.assertEqual(
            build["uses"], "./.github/workflows/flutter-build.yml"
        )
        with_block = build["with"]
        self.assertTrue(with_block["upload-artifact"])
        self.assertEqual(with_block["upload-tag"], "sasthotech-test")
        self.assertEqual(with_block["build-profile"], "sasthotech-desktop")
        self.assertEqual(
            json.loads(with_block["windows-matrix"]),
            [EXPECTED_WINDOWS_MATRIX[0]],
        )
        self.assertEqual(
            json.loads(with_block["linux-matrix"]),
            [EXPECTED_LINUX_MATRIX[0]],
        )
        self.assertEqual(
            json.loads(with_block["macos-matrix"]), EXPECTED_MACOS_MATRIX
        )


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
