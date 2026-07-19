# Sasthotech Custom Client — Server Config Injection + Preset Password

Date: 2026-07-19
Status: Approved (approach A; amended same day to add branding)

## Context

Sasthotech self-hosts a RustDesk server (hbbs/hbbr) at `185.202.236.146`. Stock clients require manual Network configuration (ID server, relay server, key) on every machine, currently done by remoting in with another tool. Goal: a custom-built client, distributed from Sasthotech's own URL, that connects to the Sasthotech server out of the box and allows unattended access via a preset permanent password.

## Requirements (confirmed with user)

1. Inject exactly three network values, hardcoded but easy to change later:
   - ID server (`custom-rendezvous-server`): `185.202.236.146`
   - Relay server (`relay-server`): `185.202.236.146`
   - Key (`key`): `K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=`
   - API server: left empty (RustDesk auto-derives from ID server host).
2. Preset permanent password, **overridable**: works on every fresh install; if a machine sets its own permanent password locally, the local one wins on that machine. Password value supplied out-of-band (not recorded in this doc — see Security).
3. Injected values are **prefilled but editable** in Settings → Network (defaults, not locks).
4. All client settings remain enabled/editable (stock OSS behavior; nothing locked or hidden).
5. Platforms: Windows, macOS, Linux, Android. iOS out of scope.
6. Branding: app presents as **"Sasthotech Remote"** (window titles, tray, dialogs, installer artifact names). Logo/icons deferred until the user supplies asset files; internal identifiers (bundle ids, package ids) unchanged this phase.

## Design

### Injection mechanism

New file `src/preset_config.rs` — the single place holding Sasthotech values:

- `PRESET_ID_SERVER`, `PRESET_RELAY_SERVER`, `PRESET_KEY` — plain string consts.
- `PRESET_PASSWORD_STORAGE`, `PRESET_PASSWORD_SALT` — the preset permanent password in RustDesk's hashed storage format (no plaintext in the binary or repo).
- `pub fn apply()` — inserts the three network values into `hbb_common::config::DEFAULT_SETTINGS` and the password storage/salt into `hbb_common::config::HARD_SETTINGS` (`"password"` / `"salt"` keys).

Call site: first statement of `load_custom_client()` in `src/common.rs`. That function already runs on every startup path — desktop main, background service, and Flutter `initialize()` on desktop and mobile (`src/flutter_ffi.rs`) — so `apply()` covers all platforms with one hook. The existing signed-`custom.txt` flow stays intact and, if ever present, loads after (its values overwrite ours, which is acceptable and unlikely).

### Why these maps

- `Config::get_option(k)` resolves `OVERWRITE_SETTINGS` → user config → `DEFAULT_SETTINGS` (`libs/hbb_common/src/config.rs`). Putting values in `DEFAULT_SETTINGS` prefills the Network UI and connection logic while letting any locally saved value win — the "hardcoded but changeable" requirement.
- Preset password: `Config::get_preset_password_storage_and_salt()` reads `HARD_SETTINGS["password"]`/`["salt"]`; `is_using_preset_password()` applies it only while the machine has no local permanent password — exactly the chosen overridable behavior. This is RustDesk's native preset mechanism (used by their commercial custom clients), so incoming-connection auth already honors it.

### Branding

`apply()` also sets `*config::APP_NAME.write() = "Sasthotech Remote"` — the same variable RustDesk's commercial custom clients set via signed `custom.txt` (`app-name`), so the UI (window titles, tray, dialogs) follows it natively. Consequences to verify during implementation:

- `is_custom_client()` returns true once the name differs from "RustDesk"; audit its call sites (e.g. updater behavior — auto-updating to official RustDesk builds must not happen, so updater disabled/neutralized is desirable).
- `APP_NAME` feeds config/data directory names and some platform install paths (Windows service name, install dir). A fresh brand name means a fresh identity/config dir on client machines — acceptable for new deployments. The space in "Sasthotech Remote" must be verified against Windows install/service-name command construction; if any call site breaks on spaces, fall back to internal name `SasthotechRemote` while keeping the spaced display where safe.
- Release artifacts renamed (e.g. `sasthotech-remote-<version>.exe`); no `host=` in filenames (would trigger the filename-config parser).
- Icons/logo: deferred until user supplies assets; bundle ids / package ids / URI scheme unchanged this phase.

### Password hash generation

During implementation, generate `storage`/`salt` from the chosen password using the repo's own functions (the same ones `preset_permanent_password_storage_is_usable_for_auth` validates against), via a temporary unit test or small helper, then paste the resulting consts. A permanent unit test asserts the embedded storage/salt authenticate the chosen password and that `apply()` populates the expected keys.

### Changing values later

Edit the consts in `src/preset_config.rs`, rebuild. Optional future upgrade (not now): read values from `option_env!()` so CI injects them without code edits.

## Security considerations

- One shared preset password initially opens every deployed machine. The password hash + salt ship inside every installer and (if the fork is public) in the repo; an offline dictionary attack against a weak password is cheap. **Recommendation: high-entropy password.** User was warned that a company-name+year pattern is guessable; value can be swapped at any time by editing one const and rebuilding.
- The plaintext password is not written to the repo, spec, or binary — only hash + salt.
- AGPL-3.0: distributing modified builds requires offering the modified source to recipients. A public fork satisfies this automatically; a private fork must provide source to clients on request.
- Unsigned Windows builds trigger SmartScreen; code-signing certificate is a later, separate concern.

## Build & distribution

- GitHub fork runs the existing `.github/workflows/flutter-build.yml` to produce Windows/macOS/Linux/Android artifacts.
- Sasthotech hosts the installers at their own download URL.

## Testing

1. Unit: `apply()` populates `DEFAULT_SETTINGS`/`HARD_SETTINGS` with expected values; embedded hash authenticates the chosen password.
2. Local macOS debug build: Network fields show `185.202.236.146` prefilled and editable; security page reflects preset password active; UI shows "Sasthotech Remote".
3. End-to-end (user-side): fresh install connects via Sasthotech server; unattended access with preset password; local password override wins.

## Non-goals

- No icon/logo change this phase (pending assets), no bundle-id/package-id changes, no settings locking, no per-client `custom.txt` generator, no iOS, no code signing.
