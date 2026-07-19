# Sasthotech Branding and Desktop CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Sasthotech Remote branding on Windows, Linux, and macOS and provide a one-click CI workflow that builds only the required desktop installers.

**Architecture:** Track one canonical Sasthotech logo plus generated platform assets. Preserve RustDesk's internal executable and service identifiers, but replace visible product metadata and patch macOS packaging to use the branded bundle path. Extend the reusable workflow with target-selection inputs, then add a small manual wrapper for Windows x64, Linux x64, macOS Intel, and macOS Apple Silicon.

**Tech Stack:** ImageMagick, macOS `iconutil`, Flutter desktop packaging, Python build script, GitHub Actions YAML.

## Global Constraints

- Visible product name is exactly `Sasthotech Remote`.
- Artifact/file slug is exactly `sasthotech-remote`.
- Use the complete supplied logo, including tagline, for main platform icons.
- Use a monochrome healthcare mark for the macOS status-bar template icon.
- Preserve internal executable name `rustdesk`, service identifiers, bundle ID, package IDs, and URI scheme.
- Do not add Android or iOS jobs.
- Existing nightly, tag, and full CI workflows must retain their current default target sets.
- Release publishing must never prevent installer artifact upload.
- Do not commit or push unless the user explicitly authorizes it.

---

### Task 1: Canonical Branding Assets

**Files:**
- Create: `res/branding/sasthotech-logo.png`
- Create: `res/branding/sasthotech-tray.svg`
- Create: `res/branding/README.md`
- Modify: `flutter/windows/runner/resources/app_icon.ico`
- Modify: `flutter/macos/Runner/AppIcon.icns`
- Modify: `res/32x32.png`
- Modify: `res/64x64.png`
- Modify: `res/128x128.png`
- Modify: `res/128x128@2x.png`
- Modify: `res/icon.png`
- Modify: `res/mac-icon.png`
- Modify: `res/scalable.svg`
- Modify: `res/mac-tray-dark-x2.png`
- Modify: `res/mac-tray-light-x2.png`

**Interfaces:**
- Consumes: source image `/Users/shihabsararislamrafid/Downloads/Untitled design.png`
- Produces: deterministic tracked assets consumed by existing Windows, macOS, Linux, AppImage, deb, and rpm packaging.

- [ ] **Step 1: Add the canonical source image**

Run:

```bash
mkdir -p res/branding
cp "/Users/shihabsararislamrafid/Downloads/Untitled design.png" \
  res/branding/sasthotech-logo.png
```

Expected: `file res/branding/sasthotech-logo.png` reports a PNG image.

- [ ] **Step 2: Add the monochrome tray source**

Create `res/branding/sasthotech-tray.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <g fill="none" stroke="#000" stroke-width="12" stroke-linecap="round">
    <path d="M31 18v28c0 23 14 38 33 38s33-15 33-38V18"/>
    <path d="M64 84v12c0 11 8 18 18 18"/>
  </g>
  <circle cx="92" cy="112" r="10" fill="#000"/>
</svg>
```

- [ ] **Step 3: Generate the square master and platform files**

Install the development-only generator, then run:

```bash
brew install imagemagick
magick res/branding/sasthotech-logo.png -trim +repage \
  -resize '880x880>' -gravity center -background white \
  -extent 1024x1024 /tmp/sasthotech-master.png

magick /tmp/sasthotech-master.png -define icon:auto-resize=256,128,64,48,32,16 \
  flutter/windows/runner/resources/app_icon.ico

magick /tmp/sasthotech-master.png -resize 32x32 res/32x32.png
magick /tmp/sasthotech-master.png -resize 64x64 res/64x64.png
magick /tmp/sasthotech-master.png -resize 128x128 res/128x128.png
magick /tmp/sasthotech-master.png -resize 256x256 res/128x128@2x.png
magick /tmp/sasthotech-master.png -resize 256x256 res/icon.png
magick /tmp/sasthotech-master.png -resize 1024x1024 res/mac-icon.png

rm -rf /tmp/SasthotechRemote.iconset
mkdir -p /tmp/SasthotechRemote.iconset
for size in 16 32 128 256 512; do
  magick /tmp/sasthotech-master.png -resize "${size}x${size}" \
    "/tmp/SasthotechRemote.iconset/icon_${size}x${size}.png"
  double=$((size * 2))
  magick /tmp/sasthotech-master.png -resize "${double}x${double}" \
    "/tmp/SasthotechRemote.iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns /tmp/SasthotechRemote.iconset \
  -o flutter/macos/Runner/AppIcon.icns

magick -background none res/branding/sasthotech-tray.svg -resize 44x44 \
  res/mac-tray-dark-x2.png
cp res/mac-tray-dark-x2.png res/mac-tray-light-x2.png
```

Generate `res/scalable.svg` as an SVG wrapper containing the square master:

```bash
encoded=$(base64 < /tmp/sasthotech-master.png | tr -d '\n')
printf '%s\n' \
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">' \
  "  <image width=\"1024\" height=\"1024\" href=\"data:image/png;base64,$encoded\"/>" \
  '</svg>' > res/scalable.svg
```

- [ ] **Step 4: Document regeneration**

Add the commands from Steps 1–3 to `res/branding/README.md`, including:

```markdown
# Sasthotech branding assets

`sasthotech-logo.png` is the canonical supplied logo. Generated desktop assets
are committed so release builds do not require ImageMagick. Regenerate on macOS
with ImageMagick and `iconutil` using the commands below.
```

- [ ] **Step 5: Verify image files**

Run:

```bash
identify res/{32x32,64x64,128x128,128x128@2x,icon,mac-icon}.png
identify flutter/windows/runner/resources/app_icon.ico
iconutil -c iconset flutter/macos/Runner/AppIcon.icns -o /tmp/verify.iconset
test -s res/mac-tray-dark-x2.png
test -s res/scalable.svg
```

Expected: every command exits 0 and all dimensions match the filenames.

- [ ] **Step 6: Checkpoint**

Review `git diff --stat` and the rendered assets. Commit only if explicitly authorized:

```bash
git add res/branding res/*.png res/scalable.svg \
  flutter/windows/runner/resources/app_icon.ico \
  flutter/macos/Runner/AppIcon.icns
git commit -m "feat(branding): add Sasthotech desktop icons"
```

---

### Task 2: Visible Desktop Product Naming

**Files:**
- Modify: `flutter/macos/Runner/Configs/AppInfo.xcconfig:8`
- Modify: `build.py:405-426`
- Modify: `.github/workflows/flutter-build.yml:821-869`
- Verify: `res/rustdesk.desktop`
- Verify: `res/rustdesk-link.desktop`

**Interfaces:**
- Consumes: `PRODUCT_NAME = Sasthotech Remote`
- Produces: macOS bundle `Sasthotech Remote.app` and installer slug `sasthotech-remote`.

- [ ] **Step 1: Add a failing source-level regression test**

Create `tests/test_sasthotech_branding.py`:

```python
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
```

- [ ] **Step 2: Run the regression test and confirm failure**

Run:

```bash
python3 -m unittest tests/test_sasthotech_branding.py
```

Expected: FAIL because the macOS product and bundle constants are not branded.

- [ ] **Step 3: Make macOS bundle handling explicit**

In `flutter/macos/Runner/Configs/AppInfo.xcconfig` set:

```xcconfig
PRODUCT_NAME = Sasthotech Remote
```

Near `build_flutter_dmg()` in `build.py`, define and use:

```python
MACOS_APP_BUNDLE = "Sasthotech Remote.app"


def build_flutter_dmg(version, features):
    # existing build steps remain unchanged
    app_path = f"./build/macos/Build/Products/Release/{MACOS_APP_BUNDLE}"
    system2(
        f'cp -rf ../target/release/service "{app_path}/Contents/MacOS/"'
    )
```

Replace hardcoded `RustDesk.app` paths in the active macOS Flutter workflow
with `Sasthotech Remote.app`, quoting every shell path. Rename generated DMGs
and artifact display names to `sasthotech-remote-<version>-<arch>.dmg`.

- [ ] **Step 4: Run the source-level tests**

Run:

```bash
python3 -m unittest tests/test_sasthotech_branding.py
```

Expected: 2 tests pass.

- [ ] **Step 5: Verify no active branded macOS path remains mismatched**

Run:

```bash
rg -n 'RustDesk\.app' build.py .github/workflows/flutter-build.yml \
  flutter/macos/Runner/Configs/AppInfo.xcconfig
```

Expected: no active Flutter-build path uses `RustDesk.app`; comments or legacy
non-Flutter packaging references must be reviewed individually.

- [ ] **Step 6: Checkpoint**

Commit only if explicitly authorized:

```bash
git add tests/test_sasthotech_branding.py build.py \
  flutter/macos/Runner/Configs/AppInfo.xcconfig \
  .github/workflows/flutter-build.yml res/*.desktop
git commit -m "feat(branding): apply Sasthotech desktop name"
```

---

### Task 3: Selectable Reusable Desktop Matrices

**Files:**
- Modify: `.github/workflows/flutter-build.yml`
- Modify: `.github/workflows/flutter-nightly.yml` only if needed to preserve explicit defaults
- Modify: `.github/workflows/flutter-tag.yml` only if needed to preserve explicit defaults
- Test: `tests/test_sasthotech_workflow.py`

**Interfaces:**
- Produces workflow-call inputs:
  - `build-profile: full|sasthotech-desktop`
  - `windows-matrix: JSON string`
  - `windows-helper-matrix: JSON string`
  - `macos-matrix: JSON string`
  - `linux-matrix: JSON string`
- Existing callers omit these inputs and retain full-build defaults.

- [ ] **Step 1: Write failing workflow-selection tests**

Create `tests/test_sasthotech_workflow.py` using `yaml.safe_load` when PyYAML is
available, with a text fallback so the test has no required package:

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".github/workflows/flutter-build.yml"
WRAPPER = ROOT / ".github/workflows/sasthotech-desktop.yml"


class WorkflowTests(unittest.TestCase):
    def test_reusable_workflow_has_desktop_profile(self):
        text = BUILD.read_text()
        self.assertIn("build-profile:", text)
        self.assertIn("windows-matrix:", text)
        self.assertIn("macos-matrix:", text)
        self.assertIn("linux-matrix:", text)
        self.assertIn("fromJSON(inputs.windows-matrix)", text)

    def test_manual_wrapper_selects_only_confirmed_targets(self):
        text = WRAPPER.read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("x86_64-pc-windows-msvc", text)
        self.assertIn("x86_64-unknown-linux-gnu", text)
        self.assertIn("x86_64-apple-darwin", text)
        self.assertIn("aarch64-apple-darwin", text)
        self.assertNotIn("android", text.lower())
        self.assertNotIn("ios", text.lower())
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
python3 -m unittest tests/test_sasthotech_workflow.py
```

Expected: FAIL because the wrapper and matrix inputs do not exist.

- [ ] **Step 3: Add reusable-workflow inputs**

Add string inputs under `workflow_call.inputs`. Defaults must be JSON arrays
equivalent to the current hardcoded matrices, preserving all existing callers.
Change the four selected matrices to:

```yaml
strategy:
  fail-fast: false
  matrix:
    job: ${{ fromJSON(inputs.windows-matrix) }}
```

Use the corresponding input for helper, macOS, and Linux jobs. Add:

```yaml
build-profile:
  type: string
  default: "full"
```

Add this job condition to iOS, Android, Windows Sciter, Linux Sciter, AppImage,
Flatpak, web, and aggregate unsigned-release jobs:

```yaml
if: inputs.build-profile != 'sasthotech-desktop'
```

Where a job already has an `if`, combine expressions with `&&`.

- [ ] **Step 4: Run the workflow-selection tests**

Run:

```bash
python3 -m unittest tests/test_sasthotech_workflow.py
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/flutter-build.yml"); puts "valid"'
```

Expected: tests pass and Ruby prints `valid`.

- [ ] **Step 5: Checkpoint**

Commit only if explicitly authorized:

```bash
git add .github/workflows/flutter-build.yml tests/test_sasthotech_workflow.py
git commit -m "ci: add selectable desktop build profile"
```

---

### Task 4: One-Click Sasthotech Desktop Workflow

**Files:**
- Create: `.github/workflows/sasthotech-desktop.yml`
- Modify: `.github/workflows/flutter-build.yml` installer upload steps
- Test: `tests/test_sasthotech_workflow.py`

**Interfaces:**
- Consumes: matrix inputs from Task 3.
- Produces: downloadable Windows x64 `.exe`/`.msi`, Linux x64 `.deb`/`.rpm`,
  macOS Intel `.dmg`, and macOS Apple Silicon `.dmg`.

- [ ] **Step 1: Create the manual wrapper**

Create `.github/workflows/sasthotech-desktop.yml`:

```yaml
name: Sasthotech Desktop Build

on:
  workflow_dispatch:

jobs:
  build:
    uses: ./.github/workflows/flutter-build.yml
    secrets: inherit
    with:
      upload-artifact: true
      upload-tag: "sasthotech-test"
      build-profile: "sasthotech-desktop"
      windows-helper-matrix: >-
        [{"target":"windows-2022","platform":"x64"}]
      windows-matrix: >-
        [{"target":"x86_64-pc-windows-msvc","os":"windows-2022","arch":"x86_64","flutter-arch":"x64","vcpkg-triplet":"x64-windows-static","build-args":"--vram"}]
      macos-matrix: >-
        [{"target":"x86_64-apple-darwin","os":"macos-15-intel","extra-build-args":"","arch":"x86_64","vcpkg-triplet":"x64-osx"},{"target":"aarch64-apple-darwin","os":"macos-14","extra-build-args":"--screencapturekit","arch":"aarch64","vcpkg-triplet":"arm64-osx"}]
      linux-matrix: >-
        [{"arch":"x86_64","target":"x86_64-unknown-linux-gnu","distro":"ubuntu18.04","on":"ubuntu-22.04","deb_arch":"amd64","vcpkg-triplet":"x64-linux"}]
```

- [ ] **Step 2: Upload final Windows installers**

After MSI creation and before release publishing, add:

```yaml
- name: Upload Sasthotech Windows installers
  if: env.UPLOAD_ARTIFACT == 'true'
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
  with:
    name: sasthotech-remote-windows-${{ matrix.job.arch }}
    path: |
      SignOutput/*.exe
      SignOutput/*.msi
    if-no-files-found: error
```

Rename copies in `SignOutput` to the `sasthotech-remote` slug while retaining
the internal executable bundled inside.

- [ ] **Step 3: Make Linux and macOS artifacts strict**

For Linux, upload `.deb` and `.rpm` together under
`sasthotech-remote-linux-x86_64`, using `if-no-files-found: error`. Ensure this
upload occurs before optional release publishing.

For macOS, use artifact names:

```yaml
name: sasthotech-remote-macos-${{ matrix.job.arch }}
path: sasthotech-remote-${{ env.VERSION }}-${{ matrix.job.arch }}.dmg
if-no-files-found: error
```

- [ ] **Step 4: Extend and run workflow tests**

Add assertions that installer upload appears before each publish step and that
every artifact uses `if-no-files-found: error`.

Run:

```bash
python3 -m unittest tests/test_sasthotech_workflow.py
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/sasthotech-desktop.yml"); puts "valid"'
git diff --check
```

Expected: all tests pass, YAML prints `valid`, and `git diff --check` is empty.

- [ ] **Step 5: Checkpoint**

Commit only if explicitly authorized:

```bash
git add .github/workflows tests/test_sasthotech_workflow.py
git commit -m "ci: add Sasthotech desktop installer build"
```

---

### Task 5: CI and Platform Smoke Verification

**Files:**
- Verify only; document results in the GitHub Actions run.

- [ ] **Step 1: Run local static checks**

Run:

```bash
python3 -m unittest tests/test_sasthotech_branding.py \
  tests/test_sasthotech_workflow.py
git diff --check
```

Expected: all tests pass and no whitespace errors.

- [ ] **Step 2: Trigger the manual workflow**

After an explicitly authorized push:

```bash
gh workflow run "Sasthotech Desktop Build" --ref main
gh run list --workflow sasthotech-desktop.yml --limit 1
```

Expected: one run with only Windows x64, Linux x64, macOS Intel, macOS Apple
Silicon, bridge generation, and Windows x64 helper jobs.

- [ ] **Step 3: Verify artifacts**

Run:

```bash
run_id=$(gh run list --workflow sasthotech-desktop.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run_id" --exit-status
gh run view "$run_id" --json artifacts,jobs
```

Expected: successful build jobs and four platform artifact groups containing
Windows `.exe`/`.msi`, Linux `.deb`/`.rpm`, and two macOS `.dmg` files.

- [ ] **Step 4: Perform manual branding smoke checks**

- Windows: installer and Start menu show Sasthotech branding; remote service
  still starts under its existing internal identifier.
- Linux: launcher shows `Sasthotech Remote`; deb/rpm installs and starts.
- macOS Intel and Apple Silicon: Finder/Dock show `Sasthotech Remote`, the DMG
  opens, and the status-bar template remains visible in light and dark mode.

- [ ] **Step 5: Final status**

Run `git status --short --branch` and report all verification evidence. Do not
claim the cross-platform build passes unless the GitHub Actions run exits 0.
