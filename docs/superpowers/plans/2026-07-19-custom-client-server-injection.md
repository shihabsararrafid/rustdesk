# Sasthotech Custom Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a RustDesk client that ships pre-configured for Sasthotech's self-hosted server (ID/relay/key), starts with a preset overridable permanent password, and presents as "Sasthotech Remote" — so clients install and connect with zero manual setup.

**Architecture:** A single new module `src/preset_config.rs` holds all Sasthotech constants and an `apply()` function. `apply()` seeds `hbb_common::config::DEFAULT_SETTINGS` (network values — prefilled but user-editable), `HARD_SETTINGS` (preset password storage + salt — native RustDesk preset-password mechanism), and `APP_NAME` (branding). It is called as the first statement of `load_custom_client()` in `src/common.rs`, which runs on every startup path (desktop `core_main`, background service, and Flutter `initialize()` on desktop + mobile) — one hook, all platforms. The auto-updater is neutralized so clients are never pointed at official RustDesk builds. Static packaging strings (macOS/Android/Linux) are swapped for display.

**Tech Stack:** Rust (core + `hbb_common` submodule), Flutter (UI, reads app name from Rust core via FFI). Build/CI via existing `.github/workflows/flutter-build.yml`.

## Global Constraints

Copy these exact values; every task's requirements include this section.

- ID server (`custom-rendezvous-server`): `185.202.236.146`
- Relay server (`relay-server`): `185.202.236.146`
- Key (`key`): `K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=`
- API server: leave empty (auto-derived from ID host).
- Network values go into `DEFAULT_SETTINGS` (prefilled, **editable** — never `OVERWRITE_SETTINGS`).
- Preset password: **overridable** (local permanent password, once set on a machine, wins over the preset). Stored as hash only — **no plaintext** in repo, spec, plan, or binary.
- Preset password storage (hash): `00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=`
- Preset password salt: `2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE`
- App display name: `Sasthotech Remote` (fallback internal `SasthotechRemote` only if a Windows service/path call site breaks on the space).
- Platforms: Windows, macOS, Linux, Android. No iOS.
- No logo/icon change this phase; no bundle-id/package-id changes; no settings locking.
- All constants live in ONE file (`src/preset_config.rs`) so future changes are a single-file edit + rebuild.
- Values verified against real source during planning: option keys `custom-rendezvous-server` / `relay-server` / `key` (`libs/hbb_common/src/config.rs:2935-2954`); preset password read at `config.rs:2782` (`HARD_SETTINGS["password"]`/`["salt"]`); preset auth at `src/server/connection.rs:2329-2331`; app name at `config.rs:72` (`APP_NAME`); Flutter reads it via `nSync()`.

---

### Task 1: Preset config module — network injection + branding

**Files:**
- Create: `src/preset_config.rs`
- Modify: `src/lib.rs` (add `mod preset_config;` near the other top-level `mod` declarations, ~line 45)
- Modify: `src/common.rs` (first line of `pub fn load_custom_client()`, ~line 2083)

**Interfaces:**
- Produces: `crate::preset_config::apply()` — seeds `DEFAULT_SETTINGS` with the three network values and sets `APP_NAME`. Idempotent (safe to call repeatedly; uses `entry().or_insert` semantics via direct insert — later real `custom.txt`, if ever present, still overrides).
- Produces consts: `PRESET_ID_SERVER`, `PRESET_RELAY_SERVER`, `PRESET_KEY`, `PRESET_APP_NAME` (`&str`).
- Consumes: `hbb_common::config::{DEFAULT_SETTINGS, APP_NAME}`, key constants `hbb_common::config::keys::{OPTION_CUSTOM_RENDEZVOUS_SERVER, OPTION_RELAY_SERVER, OPTION_KEY}`.

- [ ] **Step 1: Write the failing test**

Create `src/preset_config.rs` with only the test module first:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use hbb_common::config;

    #[test]
    fn test_apply_seeds_network_defaults_and_app_name() {
        apply();
        let d = config::DEFAULT_SETTINGS.read().unwrap();
        assert_eq!(
            d.get(config::keys::OPTION_CUSTOM_RENDEZVOUS_SERVER).map(String::as_str),
            Some(PRESET_ID_SERVER)
        );
        assert_eq!(
            d.get(config::keys::OPTION_RELAY_SERVER).map(String::as_str),
            Some(PRESET_RELAY_SERVER)
        );
        assert_eq!(
            d.get(config::keys::OPTION_KEY).map(String::as_str),
            Some(PRESET_KEY)
        );
        assert_eq!(*config::APP_NAME.read().unwrap(), PRESET_APP_NAME);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --lib preset_config 2>&1 | tail -20`
Expected: FAIL — `cannot find function apply` / `cannot find value PRESET_ID_SERVER` (module has no implementation yet).

- [ ] **Step 3: Write minimal implementation**

Prepend to `src/preset_config.rs` (above the test module):

```rust
// Single source of truth for Sasthotech's custom-client configuration.
// Change these values and rebuild to retarget the client.
use hbb_common::config;

pub const PRESET_ID_SERVER: &str = "185.202.236.146";
pub const PRESET_RELAY_SERVER: &str = "185.202.236.146";
pub const PRESET_KEY: &str = "K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=";
pub const PRESET_APP_NAME: &str = "Sasthotech Remote";

/// Seed built-in defaults. Called once at startup from `load_custom_client()`,
/// before user config is read, so these act as editable prefilled defaults
/// (a value the user later saves locally wins via the normal option lookup).
pub fn apply() {
    *config::APP_NAME.write().unwrap() = PRESET_APP_NAME.to_owned();

    let mut d = config::DEFAULT_SETTINGS.write().unwrap();
    d.insert(
        config::keys::OPTION_CUSTOM_RENDEZVOUS_SERVER.to_owned(),
        PRESET_ID_SERVER.to_owned(),
    );
    d.insert(
        config::keys::OPTION_RELAY_SERVER.to_owned(),
        PRESET_RELAY_SERVER.to_owned(),
    );
    d.insert(config::keys::OPTION_KEY.to_owned(), PRESET_KEY.to_owned());
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --lib preset_config 2>&1 | tail -20`
Expected: PASS (`test preset_config::tests::test_apply_seeds_network_defaults_and_app_name ... ok`).

- [ ] **Step 5: Wire the module and call site**

In `src/lib.rs`, add beside the other `mod` lines (near `mod custom_server;`):

```rust
mod preset_config;
```

In `src/common.rs`, make `load_custom_client()` begin with the call. Change:

```rust
pub fn load_custom_client() {
    #[cfg(debug_assertions)]
    if let Ok(data) = std::fs::read_to_string("./custom.txt") {
```

to:

```rust
pub fn load_custom_client() {
    crate::preset_config::apply();
    #[cfg(debug_assertions)]
    if let Ok(data) = std::fs::read_to_string("./custom.txt") {
```

- [ ] **Step 6: Build to verify it compiles and wiring is valid**

Run: `cargo build --lib 2>&1 | tail -20`
Expected: builds without errors referencing `preset_config` or `load_custom_client`.

- [ ] **Step 7: Commit**

```bash
git add src/preset_config.rs src/lib.rs src/common.rs
git commit -m "Add preset_config: inject Sasthotech server defaults and app name"
```

---

### Task 2: Preset permanent password

**Files:**
- Modify: `src/preset_config.rs` (add password consts + extend `apply()` + add test)

**Interfaces:**
- Produces consts: `PRESET_PASSWORD_STORAGE`, `PRESET_PASSWORD_SALT` (`&str`).
- Extends `apply()` to insert `"password"` and `"salt"` into `hbb_common::config::HARD_SETTINGS`.
- Consumes: `hbb_common::config::HARD_SETTINGS`, `hbb_common::config::preset_permanent_password_storage_is_usable_for_auth`.

The hash format is `"00" + base64(SHA256(password || salt))` with a non-empty salt — exactly what `preset_permanent_password_storage_is_usable_for_auth` (`libs/hbb_common/src/config/permanent_password.rs:124`) accepts and what `Config::get_preset_password_storage_and_salt` (`config.rs:2782`) reads. The values in Global Constraints were generated for the agreed password. Plaintext is NOT stored anywhere.

- [ ] **Step 1: Write the failing test**

Add to the `tests` module in `src/preset_config.rs`:

```rust
    #[test]
    fn test_preset_password_is_valid_and_applied() {
        // Format must be accepted by the auth path.
        assert!(config::preset_permanent_password_storage_is_usable_for_auth(
            PRESET_PASSWORD_STORAGE,
            PRESET_PASSWORD_SALT
        ));
        apply();
        let h = config::HARD_SETTINGS.read().unwrap();
        assert_eq!(h.get("password").map(String::as_str), Some(PRESET_PASSWORD_STORAGE));
        assert_eq!(h.get("salt").map(String::as_str), Some(PRESET_PASSWORD_SALT));
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --lib preset_config::tests::test_preset_password 2>&1 | tail -20`
Expected: FAIL — `cannot find value PRESET_PASSWORD_STORAGE`.

- [ ] **Step 3: Write minimal implementation**

Add the consts after `PRESET_APP_NAME` in `src/preset_config.rs`:

```rust
// Preset permanent password (overridable). Hash only — never plaintext.
// Format: "00" + base64(SHA256(password || salt)). Regenerate via Step 5 to rotate.
pub const PRESET_PASSWORD_STORAGE: &str = "00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=";
pub const PRESET_PASSWORD_SALT: &str = "2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE";
```

Extend `apply()` — append before its closing brace, after the `d` block ends (drop the `DEFAULT_SETTINGS` write lock first by scoping, or add after it since `HARD_SETTINGS` is a different lock):

```rust
    drop(d);
    let mut h = config::HARD_SETTINGS.write().unwrap();
    h.insert("password".to_owned(), PRESET_PASSWORD_STORAGE.to_owned());
    h.insert("salt".to_owned(), PRESET_PASSWORD_SALT.to_owned());
```

(If `d` is already dropped at end of scope, just add the `h` block; keep a single `apply()` returning `()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --lib preset_config 2>&1 | tail -20`
Expected: PASS for both `test_apply_seeds_network_defaults_and_app_name` and `test_preset_password_is_valid_and_applied`.

- [ ] **Step 5: (Rotation reference — how to regenerate, do NOT commit plaintext)**

To change the password later, run this throwaway snippet (replace the password locally, never commit it), then paste the two printed consts:

```rust
// Temporary main or #[test] (delete before commit — contains plaintext):
use hbb_common::config::compute_permanent_password_h1;
use hbb_common::sodiumoxide::base64;
let password = std::env::var("SASTHO_PW").unwrap(); // pass via env, don't hardcode
let salt: String = { use hbb_common::rand::Rng; let mut r = hbb_common::rand::thread_rng();
    (0..32).map(|_| { let c = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"; c[r.gen_range(0..c.len())] as char }).collect() };
let h1 = compute_permanent_password_h1(&password, &salt);
let storage = format!("00{}", base64::encode(&h1, base64::Variant::Original));
println!("PRESET_PASSWORD_STORAGE = {storage}\nPRESET_PASSWORD_SALT = {salt}");
```

Run: `SASTHO_PW='...' cargo test ...` locally; paste output into the consts; delete the snippet. (Not part of the committed change — reference only.)

- [ ] **Step 6: Commit**

```bash
git add src/preset_config.rs
git commit -m "Seed preset overridable permanent password"
```

---

### Task 3: Neutralize auto-updater for the custom client

**Files:**
- Modify: `src/updater.rs` (early return in `check_update`, ~line 120)

**Interfaces:**
- Consumes: `crate::is_custom_client()` (`src/common.rs:2283` — true once `APP_NAME != "RustDesk"`, which Task 1 guarantees).

Rationale: `is_custom_client()` already disables the Windows MSI auto-update path (`updater.rs:122`) and `OPTION_ALLOW_AUTO_UPDATE` defaults off, but a manual "check for updates" still queries official RustDesk release URLs and would offer official builds. Gate the whole check so branded clients never fetch official binaries.

- [ ] **Step 1: Write the failing test**

Add to the bottom of `src/updater.rs` (new test module):

```rust
#[cfg(test)]
mod custom_client_tests {
    #[test]
    fn test_check_update_noops_for_custom_client() {
        // Force custom-client identity.
        *hbb_common::config::APP_NAME.write().unwrap() = "Sasthotech Remote".to_owned();
        assert!(crate::is_custom_client());
        // Should return Ok(()) immediately without attempting network I/O.
        assert!(super::check_update(false).is_ok());
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --lib updater::custom_client_tests 2>&1 | tail -20`
Expected: FAIL — test attempts real update logic (or asserts before the guard exists). If it passes accidentally because the network call is swallowed, still add the guard in Step 3 for correctness and re-run.

- [ ] **Step 3: Write minimal implementation**

At the very start of `fn check_update(manually: bool) -> ResultType<()>` in `src/updater.rs`, add:

```rust
fn check_update(manually: bool) -> ResultType<()> {
    if crate::is_custom_client() {
        // Branded build: never fetch official RustDesk releases.
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    let update_msi = crate::platform::is_msi_installed()? && !crate::is_custom_client();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --lib updater::custom_client_tests 2>&1 | tail -20`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater.rs
git commit -m "Disable update check for custom (branded) client"
```

---

### Task 4: Static packaging branding (macOS / Android / Linux)

**Files:**
- Modify: `flutter/macos/Runner/Configs/AppInfo.xcconfig:8` (`PRODUCT_NAME`)
- Modify: `flutter/android/app/src/main/AndroidManifest.xml:28` (`android:label`)
- Modify: `res/rustdesk.desktop:2` and `res/rustdesk-link.desktop:2` (`Name=`)

These affect the app bundle / launcher label shown by the OS (runtime UI text already follows `APP_NAME` from Task 1). Windows installer strings (Inno Setup) are handled by CI packaging and left to a later pass; not required for the macOS/Linux/Android builds. Icons/logo deferred.

- [ ] **Step 1: macOS product name**

Edit `flutter/macos/Runner/Configs/AppInfo.xcconfig` line 8:

```
PRODUCT_NAME = Sasthotech Remote
```

(`Info.plist` already maps `CFBundleName` → `$(PRODUCT_NAME)`, so no plist edit needed.)

- [ ] **Step 2: Android launcher label**

Edit `flutter/android/app/src/main/AndroidManifest.xml` line 28:

```xml
        android:label="Sasthotech Remote"
```

(Leave the line-49 `android:label="RustDesk Input"` for the input service, or change to `"Sasthotech Remote Input"` — cosmetic; change it for consistency.)

- [ ] **Step 3: Linux .desktop names**

Edit `res/rustdesk.desktop` line 2 and `res/rustdesk-link.desktop` line 2:

```
Name=Sasthotech Remote
```

- [ ] **Step 4: Verify no accidental `host=` in any renamed artifact string**

Run: `rg -n "host=" res/*.desktop flutter/macos/Runner/Configs/AppInfo.xcconfig flutter/android/app/src/main/AndroidManifest.xml`
Expected: no matches (a literal `host=` in a filename would trigger the exe-name config parser).

- [ ] **Step 5: Commit**

```bash
git add flutter/macos/Runner/Configs/AppInfo.xcconfig flutter/android/app/src/main/AndroidManifest.xml res/rustdesk.desktop res/rustdesk-link.desktop
git commit -m "Rebrand packaging strings to Sasthotech Remote"
```

---

### Task 5: Verification

**Files:** none (verification only)

- [ ] **Step 1: Full crate test run for the new logic**

Run: `cargo test --lib preset_config 2>&1 | tail -20` and `cargo test --lib updater::custom_client_tests 2>&1 | tail -20`
Expected: all PASS.

- [ ] **Step 2: hbb_common preset-password tests still green**

Run: `cargo test -p hbb_common permanent_password 2>&1 | tail -20`
Expected: PASS (confirms our storage/salt format matches the module's contract).

- [ ] **Step 3: Confirm no plaintext password leaked**

Run: `rg -n "<the-chosen-plaintext-password>" . || echo "clean"` (substitute the real password only in your shell — do not commit it).
Expected: `clean` (plaintext must appear nowhere in the repo).

- [ ] **Step 4: Manual smoke (documented for the user — requires Flutter + vcpkg toolchain)**

Not automated (needs `VCPKG_ROOT` with libvpx/libyuv/opus/aom + Flutter SDK). Steps for whoever has the toolchain:
1. Build/run the Flutter desktop app on macOS.
2. Settings → Network → ID/Relay server: confirm `185.202.236.146` prefilled in ID + Relay, Key prefilled, and fields are editable.
3. Window title / About shows "Sasthotech Remote".
4. Security page: permanent-password (preset) active.
5. From a second machine, connect using the preset password → unattended access works. Set a local permanent password on the first machine → the local one now overrides the preset.

- [ ] **Step 5: Final branch state**

Run: `git log --oneline -6`
Expected: commits for spec, branding amendment, and Tasks 1–4 present on `sasthotech-custom-client`. No push (local only until the user says otherwise).

---

## Self-Review Notes

- **Spec coverage:** network injection (Task 1), editable-not-locked via `DEFAULT_SETTINGS` (Task 1), preset overridable password (Task 2), branding name (Tasks 1 + 4), updater safety (Task 3), platforms via existing CI (noted), no-logo/no-lock non-goals respected. All spec sections mapped.
- **Placeholder scan:** none — all steps contain concrete code/paths/commands. The rotation snippet in Task 2 Step 5 is explicitly a reference, not a committed placeholder.
- **Type consistency:** `apply()` signature and const names (`PRESET_ID_SERVER`, `PRESET_RELAY_SERVER`, `PRESET_KEY`, `PRESET_APP_NAME`, `PRESET_PASSWORD_STORAGE`, `PRESET_PASSWORD_SALT`) are identical across Tasks 1–2 and their tests.
- **Open risk:** `APP_NAME = "Sasthotech Remote"` (with space) on Windows service/path construction is untested locally; fallback `SasthotechRemote` documented in Global Constraints. Verify on a Windows build before mass deployment.
