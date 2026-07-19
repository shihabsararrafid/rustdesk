# Sasthotech Custom Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RustDesk client that ships preconfigured for Sasthotech's self-hosted server (ID/relay/key), presents as "Sasthotech Remote", and accepts a preset permanent password for unattended access.

**Architecture:** One new module `src/preset_config.rs` holds all Sasthotech constants and an `apply()` that feeds RustDesk's existing runtime maps (`DEFAULT_SETTINGS`, `HARD_SETTINGS`, `APP_NAME`). `apply()` is called from the top of `load_custom_client()` in `src/common.rs`, which every startup path (desktop main, service, Flutter desktop/mobile init) already runs. No changes inside the `libs/hbb_common` submodule.

**Tech Stack:** Rust (main crate `rustdesk`), hbb_common submodule APIs, GitHub Actions `flutter-build.yml` for release artifacts.

## Global Constraints

- ID server default: `185.202.236.146` (option key `custom-rendezvous-server`)
- Relay server default: `185.202.236.146` (option key `relay-server`)
- Key default: `K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=` (option key `key`)
- API server: leave empty (auto-derived)
- App display name: `Sasthotech Remote`
- Preset permanent password: hashed only (storage `00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=`, salt `2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE`); plaintext NEVER committed to repo, spec, plan, or code
- Server values are defaults (editable in UI), not locks; preset password overridable by a locally set permanent password
- Auto update-check defaults off (`enable-check-update` = `N`) so clients never fetch official RustDesk builds
- Platforms: Windows, macOS, Linux, Android; iOS/icons/bundle-ids out of scope
- Do NOT `git push` anywhere until the user explicitly approves the remote (standing "don't push" order)
- AGPL-3.0: fork source must be offered to binary recipients

---

### Task 1: Build environment for `cargo test`

**Files:** none (environment only)

**Interfaces:**
- Consumes: nothing
- Produces: working `cargo check`/`cargo test` for the `rustdesk` lib crate on this macOS machine (needed by every later task)

- [ ] **Step 1: Check toolchain presence**

Run: `cargo --version && rustc --version && echo "VCPKG_ROOT=$VCPKG_ROOT" && ls "$VCPKG_ROOT/installed" 2>/dev/null`
Expected: cargo/rustc print versions. If `VCPKG_ROOT` empty or `installed` missing, do Step 2, else skip to Step 3.

- [ ] **Step 2: Install vcpkg + native deps (only if missing)**

```bash
git clone https://github.com/microsoft/vcpkg ~/vcpkg
~/vcpkg/bootstrap-vcpkg.sh
export VCPKG_ROOT=$HOME/vcpkg
~/vcpkg/vcpkg install libvpx libyuv opus aom
```

Expected: four ports report `SUCCESS` (takes tens of minutes). Persist `export VCPKG_ROOT=$HOME/vcpkg` into `~/.zshrc`.

- [ ] **Step 3: Prove the lib crate compiles**

Run: `cd /Users/shihabsararislamrafid/Documents/Sasthotech/rustdesk && VCPKG_ROOT=${VCPKG_ROOT:-$HOME/vcpkg} cargo check --lib`
Expected: finishes with `Finished` (warnings OK). If it fails on a missing native lib, install that vcpkg port and retry; do not proceed until green.

---

### Task 2: `src/preset_config.rs` — constants, `apply()`, startup hook

**Files:**
- Create: `src/preset_config.rs`
- Modify: `src/lib.rs` (add `mod preset_config;` after the `mod custom_server;` line, currently line 44 region)
- Modify: `src/common.rs:2083` (`load_custom_client()` — first statement)
- Modify: `docs/superpowers/specs/2026-07-19-custom-client-server-injection-design.md` (document update-check default)
- Test: inline `#[cfg(test)]` module in `src/preset_config.rs`

**Interfaces:**
- Consumes: `hbb_common::config::{APP_NAME, DEFAULT_SETTINGS, HARD_SETTINGS, keys, preset_permanent_password_storage_is_usable_for_auth, decode_preset_password_h1_from_storage}` (all `pub` — verified)
- Produces: `pub fn apply()` in module `preset_config` + `pub const PRESET_ID_SERVER/PRESET_RELAY_SERVER/PRESET_KEY/PRESET_APP_NAME/PRESET_PASSWORD_STORAGE/PRESET_PASSWORD_SALT: &str`. Task 3 may change `PRESET_APP_NAME`'s value only.

- [ ] **Step 1: Write the module with failing tests (no `apply()` yet)**

Create `src/preset_config.rs`:

```rust
// Single place holding all Sasthotech deployment values. To change servers,
// name, or password, edit the consts below and rebuild — nothing else
// references these values.
use hbb_common::config::{self, keys};

pub const PRESET_ID_SERVER: &str = "185.202.236.146";
pub const PRESET_RELAY_SERVER: &str = "185.202.236.146";
pub const PRESET_KEY: &str = "K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=";
pub const PRESET_APP_NAME: &str = "Sasthotech Remote";
// Hashed preset permanent password: "00" + base64(sha256(plaintext + salt)).
// The plaintext is deliberately not in the repo. To rotate the password,
// regenerate both consts (see docs/superpowers/plans/2026-07-19-sasthotech-custom-client.md, Task 2 Step 5).
pub const PRESET_PASSWORD_STORAGE: &str = "00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=";
pub const PRESET_PASSWORD_SALT: &str = "2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apply_populates_network_defaults() {
        apply();
        let d = config::DEFAULT_SETTINGS.read().unwrap();
        assert_eq!(
            d.get(keys::OPTION_CUSTOM_RENDEZVOUS_SERVER).map(|s| s.as_str()),
            Some(PRESET_ID_SERVER)
        );
        assert_eq!(
            d.get(keys::OPTION_RELAY_SERVER).map(|s| s.as_str()),
            Some(PRESET_RELAY_SERVER)
        );
        assert_eq!(d.get(keys::OPTION_KEY).map(|s| s.as_str()), Some(PRESET_KEY));
        assert_eq!(
            d.get(keys::OPTION_ENABLE_CHECK_UPDATE).map(|s| s.as_str()),
            Some("N")
        );
    }

    #[test]
    fn apply_sets_app_name() {
        apply();
        assert_eq!(config::APP_NAME.read().unwrap().as_str(), PRESET_APP_NAME);
    }

    #[test]
    fn preset_password_storage_is_valid_hashed_form() {
        apply();
        assert!(config::preset_permanent_password_storage_is_usable_for_auth(
            PRESET_PASSWORD_STORAGE,
            PRESET_PASSWORD_SALT
        ));
        assert!(config::decode_preset_password_h1_from_storage(PRESET_PASSWORD_STORAGE).is_some());
        let h = config::HARD_SETTINGS.read().unwrap();
        assert_eq!(
            h.get("password").map(|s| s.as_str()),
            Some(PRESET_PASSWORD_STORAGE)
        );
        assert_eq!(h.get("salt").map(|s| s.as_str()), Some(PRESET_PASSWORD_SALT));
    }
}
```

In `src/lib.rs`, directly under `mod custom_server;` add:

```rust
mod preset_config;
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test --lib preset_config 2>&1 | tail -20`
Expected: COMPILE ERROR `cannot find function `apply` in this scope` (that is the failing state; do not skip observing it).

- [ ] **Step 3: Implement `apply()`**

Add above the `#[cfg(test)]` module in `src/preset_config.rs`:

```rust
pub fn apply() {
    *config::APP_NAME.write().unwrap() = PRESET_APP_NAME.to_owned();
    {
        let mut defaults = config::DEFAULT_SETTINGS.write().unwrap();
        defaults.insert(
            keys::OPTION_CUSTOM_RENDEZVOUS_SERVER.to_owned(),
            PRESET_ID_SERVER.to_owned(),
        );
        defaults.insert(
            keys::OPTION_RELAY_SERVER.to_owned(),
            PRESET_RELAY_SERVER.to_owned(),
        );
        defaults.insert(keys::OPTION_KEY.to_owned(), PRESET_KEY.to_owned());
        defaults.insert(
            keys::OPTION_ENABLE_CHECK_UPDATE.to_owned(),
            "N".to_owned(),
        );
    }
    let mut hard = config::HARD_SETTINGS.write().unwrap();
    hard.insert("password".to_owned(), PRESET_PASSWORD_STORAGE.to_owned());
    hard.insert("salt".to_owned(), PRESET_PASSWORD_SALT.to_owned());
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test --lib preset_config 2>&1 | tail -10`
Expected: `test result: ok. 3 passed`

- [ ] **Step 5: Verify the committed hash matches the real password (nothing committed here)**

Run (enters password interactively so it never lands in repo/shell history):

```bash
python3 - <<'EOF'
import hashlib, base64, getpass
pw = getpass.getpass('preset password: ')
salt = '2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE'
print('00' + base64.b64encode(hashlib.sha256((pw + salt).encode()).digest()).decode())
EOF
```

Expected: output equals `00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=` when the agreed password is typed. If it does not match, regenerate both consts with this same snippet (new random 32-char salt) and update the file.

- [ ] **Step 6: Hook startup**

In `src/common.rs`, `load_custom_client()` (line 2083) — make the first statement:

```rust
pub fn load_custom_client() {
    crate::preset_config::apply();
    #[cfg(debug_assertions)]
    if let Ok(data) = std::fs::read_to_string("./custom.txt") {
```

(Leave the rest of the function untouched; a signed `custom.txt`, if ever present, intentionally overrides our presets.)

- [ ] **Step 7: Sync the spec**

In `docs/superpowers/specs/2026-07-19-custom-client-server-injection-design.md`, in the `### Injection mechanism` section, append one bullet to the `apply()` description list:

```markdown
- `DEFAULT_SETTINGS["enable-check-update"] = "N"` — clients must not auto-fetch official RustDesk updates, which would replace the Sasthotech build; users can re-enable manually, and Sasthotech distributes updates from its own URL.
```

- [ ] **Step 8: Full lib check + commit**

Run: `cargo check --lib && cargo test --lib preset_config 2>&1 | tail -5`
Expected: check `Finished`, tests `3 passed`.

```bash
git add src/preset_config.rs src/lib.rs src/common.rs docs/superpowers/specs/2026-07-19-custom-client-server-injection-design.md
git commit -m "Add Sasthotech preset config: server defaults, app name, preset password"
```

---

### Task 3: Branding safety audit (space in "Sasthotech Remote")

**Files:**
- Possibly modify: `src/preset_config.rs` (only the `PRESET_APP_NAME` value)

**Interfaces:**
- Consumes: `PRESET_APP_NAME` from Task 2
- Produces: verified-safe final app name value; audit summary in the commit message

- [ ] **Step 1: Audit Windows install/service command construction**

Run: `rg -n "get_app_name\(\)" src/platform/windows.rs`
For each hit that builds a shell command (`run_cmds`, `sc create`, `reg add`, paths), open the surrounding lines and check the interpolated name is inside double quotes. Record files:lines of any UNQUOTED interpolation.

- [ ] **Step 2: Audit IPC/paths**

Run: `rg -n "APP_NAME" libs/hbb_common/src/config.rs src/ipc.rs src/platform/mod.rs | head -30`
Same check: name used in filesystem paths is fine (spaces legal); name used in unquoted shell strings is not.

- [ ] **Step 3: Decide**

Decision rule: if Step 1/2 found at least one unquoted shell interpolation, change in `src/preset_config.rs`:

```rust
pub const PRESET_APP_NAME: &str = "SasthotechRemote";
```

Otherwise keep `"Sasthotech Remote"`. Do not attempt to fix RustDesk's quoting in this task.

- [ ] **Step 4: Confirm Flutter follows the Rust-side name**

Run: `rg -rn "mainGetAppName|main_get_app_name" flutter/lib | head` — wrong flag guard: use `rg -n "mainGetAppName|main_get_app_name" flutter/lib | head -10`
Expected: hits in Flutter UI code (title bars/dialogs read the name over FFI). Record known limitation: macOS `.app` bundle name and bundle ids stay `RustDesk` this phase.

- [ ] **Step 5: Re-test + commit**

Run: `cargo test --lib preset_config 2>&1 | tail -5`
Expected: `3 passed` (tests compare against the const, so they pass for either name value).

```bash
git add -A src/preset_config.rs
git commit -m "Audit app-name interpolation for spaces; finalize brand name" --allow-empty
```

(`--allow-empty` because a fully-quoted audit result changes no code; the commit records the audit outcome in its message body.)

---

### Task 4: Verification gate (local)

**Files:** none

**Interfaces:**
- Consumes: Tasks 2-3 output
- Produces: green verification evidence required before any push/build handoff

- [ ] **Step 1: Full test target**

Run: `cargo test --lib preset_config -- --nocapture 2>&1 | tail -6`
Expected: `test result: ok. 3 passed; 0 failed`

- [ ] **Step 2: Whole-lib compile with default features**

Run: `cargo check --lib 2>&1 | tail -3`
Expected: `Finished` with no errors.

- [ ] **Step 3: Flutter-feature compile (CI parity)**

Run: `cargo check --lib --features flutter 2>&1 | tail -3`
Expected: `Finished`. If this fails on missing `flutter_rust_bridge` generated file (`src/bridge_generated.rs` style errors), note it as CI-only feature and rely on Task 5's workflow build — do not hand-write generated files.

---

### Task 5: Fork remote + CI installers (USER GATE: push approval)

**Files:**
- Possibly modify: `.github/workflows/flutter-build.yml` (trigger only)

**Interfaces:**
- Consumes: committed branch `sasthotech-custom-client`
- Produces: Windows/macOS/Linux/Android installer artifacts for Sasthotech's download URL

- [ ] **Step 1: USER GATE — remote + push approval**

Ask the user for: (a) their GitHub repo URL (suggest a fork under the Sasthotech org; private is AGPL-OK if source is offered to clients on request), (b) explicit "yes, push". The standing order is "don't push" — do NOT run `git push` before this answer.

- [ ] **Step 2: Add remote and push branch**

```bash
git remote add sasthotech <URL-from-user>
git push -u sasthotech sasthotech-custom-client
```

Expected: branch visible on GitHub.

- [ ] **Step 3: Check workflow triggers**

Run: `rg -n "^on:" -A 10 .github/workflows/flutter-build.yml`
If `workflow_dispatch:` is absent, add it under `on:` (keep existing triggers), commit, push:

```yaml
on:
  workflow_dispatch:
```

- [ ] **Step 4: Run the build workflow**

Trigger `flutter-build.yml` on branch `sasthotech-custom-client` via GitHub UI or `gh workflow run flutter-build.yml --ref sasthotech-custom-client`.
Expected: Windows/Linux/Android jobs produce artifacts. Known-likely failures: macOS signing/notarization and store-upload steps (no Apple/Play secrets) — for those, comment out or `if: false` the signing/upload steps and keep the unsigned artifact upload. Iterate until each target platform yields an installable artifact. Success criteria: downloadable `.exe`, `.dmg` (unsigned), `.deb`/`.AppImage`, `.apk`.

- [ ] **Step 5: Hand artifacts to user**

User hosts them at the Sasthotech download URL. Remind: rename artifacts if desired (e.g. `sasthotech-remote-1.4.2.exe`) but NEVER include `host=` in a filename (triggers RustDesk's filename-config parser).

---

### Task 6: Acceptance (user-executed, guided)

**Files:** none

**Interfaces:**
- Consumes: Task 5 artifacts
- Produces: user sign-off

- [ ] **Step 1: Fresh Windows machine/VM** — install the `.exe`. Settings → Network shows ID `185.202.236.146`, Relay `185.202.236.146`, Key `K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=`, all editable. UI titles show the brand name.
- [ ] **Step 2: Unattended access** — from the Sasthotech console machine, connect to the new install's ID using the agreed preset password, with nobody clicking Accept on the remote side. Expected: session opens.
- [ ] **Step 3: Override behavior** — on the client machine set a local permanent password in Security; reconnect: preset password now rejected, local one accepted.
- [ ] **Step 4: No update nag** — Sett