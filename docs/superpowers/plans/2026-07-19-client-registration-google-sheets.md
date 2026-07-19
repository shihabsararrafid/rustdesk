# Client Registration and Google Sheets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a desktop client first registers successfully with the Sasthotech RustDesk server, append one deduplicated Google Sheets row and email `shihabsararrafid@gmail.com` without affecting remote-control availability.

**Architecture:** A small desktop-only Rust module owns installation identity, payload creation, persistent completion state, and a bounded asynchronous HTTPS request. The rendezvous mediator triggers it only after an authoritative registration response. A Google Apps Script web app validates and deduplicates requests, writes the sheet, and sends the email.

**Tech Stack:** Rust, Tokio, Reqwest, Serde, UUID, Chrono, Google Apps Script, Google Sheets, MailApp, Node's built-in test runner.

## Global Constraints

- Desktop platforms only: Windows, Linux, and macOS.
- Trigger after `RegisterPeerResponse` confirms an existing registration or `RegisterPkResponse::OK` confirms a new registration.
- Record installation UUID, RustDesk ID, hostname, OS, app version, and UTC timestamp.
- Do not collect public IP, local username, or hardware details.
- Notification failures must never block startup, rendezvous registration, or remote access.
- Google account, email, and Sheet credentials never enter source or client binaries.
- Build-injected validation token is anti-spam only; it is not strong authentication.
- Never log the webhook token.
- Do not add a nested Tokio runtime or hold a lock across `.await`.
- Do not add Rust dependencies; required crates already exist.
- Do not commit or push unless the user explicitly authorizes it.

---

### Task 1: Installation State and Registration Payload

**Files:**
- Create: `src/install_registration.rs`
- Modify: `src/lib.rs:43-48`

**Interfaces:**
- Produces:
  - `pub fn notify_after_server_registration()`
  - `fn get_or_create_installation_id() -> String`
  - `RegistrationPayload`
- Consumes existing `Config`, `crate::common::hostname()`, `crate::VERSION`,
  `uuid`, `chrono`, and `serde`.

- [ ] **Step 1: Add failing pure-data tests**

Create `src/install_registration.rs` with types and tests first:

```rust
use serde::{Deserialize, Serialize};

const INSTALLATION_ID_OPTION: &str = "sasthotech-installation-id";
const NOTIFIED_OPTION: &str = "sasthotech-registration-notified";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct RegistrationPayload {
    installation_id: String,
    rustdesk_id: String,
    hostname: String,
    os: String,
    app_version: String,
    registered_at: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_serialization_contains_only_approved_fields() {
        let payload = RegistrationPayload {
            installation_id: "3d9d36e2-70c1-4c1d-a63d-cf45f314e922".into(),
            rustdesk_id: "123456789".into(),
            hostname: "front-desk".into(),
            os: "windows".into(),
            app_version: "1.4.9".into(),
            registered_at: "2026-07-19T12:00:00Z".into(),
        };
        let value = serde_json::to_value(payload).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 6);
        assert!(value.get("public_ip").is_none());
        assert!(value.get("username").is_none());
        assert!(value.get("hardware").is_none());
    }

    #[test]
    fn valid_installation_id_is_reused() {
        let existing = "3d9d36e2-70c1-4c1d-a63d-cf45f314e922";
        assert_eq!(normalize_or_generate_id(existing, || unreachable!()), existing);
    }

    #[test]
    fn invalid_installation_id_is_replaced() {
        let generated = "d9994a64-b08b-4657-8d2f-ac74793f8288";
        assert_eq!(
            normalize_or_generate_id("not-a-uuid", || generated.to_owned()),
            generated
        );
    }
}
```

- [ ] **Step 2: Run tests and confirm failure**

Temporarily expose the module in `src/lib.rs`:

```rust
#[cfg(any(target_os = "windows", target_os = "linux", target_os = "macos"))]
mod install_registration;
```

Run:

```bash
cargo test --lib install_registration::tests -- --test-threads=1
```

Expected: FAIL because `normalize_or_generate_id` is undefined.

- [ ] **Step 3: Implement installation identity and payload construction**

Add:

```rust
use chrono::Utc;
use hbb_common::config::Config;
use uuid::Uuid;

fn normalize_or_generate_id(
    existing: &str,
    generate: impl FnOnce() -> String,
) -> String {
    if Uuid::parse_str(existing).is_ok() {
        existing.to_owned()
    } else {
        generate()
    }
}

fn get_or_create_installation_id() -> String {
    let existing = Config::get_option(INSTALLATION_ID_OPTION);
    let installation_id =
        normalize_or_generate_id(&existing, || Uuid::new_v4().to_string());
    if installation_id != existing {
        Config::set_option(
            INSTALLATION_ID_OPTION.to_owned(),
            installation_id.clone(),
        );
    }
    installation_id
}

fn build_payload() -> RegistrationPayload {
    RegistrationPayload {
        installation_id: get_or_create_installation_id(),
        rustdesk_id: Config::get_id(),
        hostname: crate::common::hostname(),
        os: std::env::consts::OS.to_owned(),
        app_version: crate::VERSION.to_owned(),
        registered_at: Utc::now().to_rfc3339(),
    }
}

fn is_notified() -> bool {
    Config::get_option(NOTIFIED_OPTION) == "Y"
}

fn mark_notified() {
    Config::set_option(NOTIFIED_OPTION.to_owned(), "Y".to_owned());
}
```

- [ ] **Step 4: Run tests**

Run:

```bash
cargo test --lib install_registration::tests -- --test-threads=1
```

Expected: all module tests pass.

- [ ] **Step 5: Checkpoint**

Commit only if explicitly authorized:

```bash
git add src/install_registration.rs src/lib.rs
git commit -m "feat(client): add installation registration state"
```

---

### Task 2: Non-Blocking Webhook Delivery

**Files:**
- Modify: `src/install_registration.rs`
- Modify: `src/rendezvous_mediator.rs:343-380`

**Interfaces:**
- Compile-time environment:
  - `SASTHOTECH_REGISTRATION_URL`
  - `SASTHOTECH_REGISTRATION_TOKEN`
- HTTP request body:
  - `token`
  - flattened `RegistrationPayload`
- Apps Script response: `{"accepted":true,"duplicate":false}` or
  `{"accepted":true,"duplicate":true}`.

- [ ] **Step 1: Add failing response and configuration tests**

Add:

```rust
#[derive(Serialize)]
struct RegistrationRequest<'a> {
    token: &'a str,
    #[serde(flatten)]
    payload: &'a RegistrationPayload,
}

#[derive(Debug, Deserialize)]
struct RegistrationResponse {
    accepted: bool,
    #[serde(default)]
    duplicate: bool,
}

fn parse_response(body: &str) -> bool {
    serde_json::from_str::<RegistrationResponse>(body)
        .map(|response| response.accepted)
        .unwrap_or(false)
}

#[cfg(test)]
mod response_tests {
    use super::*;

    #[test]
    fn accepts_new_and_duplicate_success_responses() {
        assert!(parse_response(r#"{"accepted":true,"duplicate":false}"#));
        assert!(parse_response(r#"{"accepted":true,"duplicate":true}"#));
    }

    #[test]
    fn rejects_malformed_or_negative_responses() {
        assert!(!parse_response("not json"));
        assert!(!parse_response(r#"{"accepted":false}"#));
    }
}
```

- [ ] **Step 2: Run tests and confirm delivery entry point is absent**

Run:

```bash
cargo test --lib install_registration -- --test-threads=1
rg -n "notify_after_server_registration" src/rendezvous_mediator.rs
```

Expected: data tests pass; `rg` returns no call sites.

- [ ] **Step 3: Implement bounded asynchronous delivery**

Add:

```rust
use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};

static IN_FLIGHT: AtomicBool = AtomicBool::new(false);
static EXHAUSTED_THIS_PROCESS: AtomicBool = AtomicBool::new(false);

fn endpoint_config() -> Option<(&'static str, &'static str)> {
    let url = option_env!("SASTHOTECH_REGISTRATION_URL")?.trim();
    let token = option_env!("SASTHOTECH_REGISTRATION_TOKEN")?.trim();
    if url.starts_with("https://") && !token.is_empty() {
        Some((url, token))
    } else {
        None
    }
}

async fn send_registration(
    url: &str,
    token: &str,
    payload: &RegistrationPayload,
) -> Result<bool, reqwest::Error> {
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::limited(3))
        .build()?;
    let response = client
        .post(url)
        .json(&RegistrationRequest { token, payload })
        .send()
        .await?
        .error_for_status()?;
    Ok(parse_response(&response.text().await?))
}

pub fn notify_after_server_registration() {
    if is_notified() || EXHAUSTED_THIS_PROCESS.load(Ordering::SeqCst) {
        return;
    }
    let Some((url, token)) = endpoint_config() else {
        return;
    };
    if IN_FLIGHT
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return;
    }
    let payload = build_payload();
    tokio::spawn(async move {
        for delay_seconds in [0, 30, 120] {
            if delay_seconds > 0 {
                tokio::time::sleep(Duration::from_secs(delay_seconds)).await;
            }
            match send_registration(url, token, &payload).await {
                Ok(true) => {
                    mark_notified();
                    IN_FLIGHT.store(false, Ordering::SeqCst);
                    return;
                }
                Ok(false) => {
                    log::warn!("Client registration webhook rejected the payload")
                }
                Err(error) => {
                    log::warn!("Client registration webhook failed: {error}")
                }
            }
        }
        EXHAUSTED_THIS_PROCESS.store(true, Ordering::SeqCst);
        IN_FLIGHT.store(false, Ordering::SeqCst);
    });
}
```

Do not retry inside the rendezvous handler. The background task tries at most
three times per process with 0, 30, and 120-second delays. A later launch retries
when the completion flag is still unset.

- [ ] **Step 4: Hook both authoritative success paths**

In `RegisterPeerResponse`:

```rust
if rpr.request_pk {
    log::info!("request_pk received from {}", self.host);
    self.register_pk(sink).await?;
} else {
    #[cfg(any(target_os = "windows", target_os = "linux", target_os = "macos"))]
    crate::install_registration::notify_after_server_registration();
}
```

In `RegisterPkResponse::OK`, after key confirmation:

```rust
#[cfg(any(target_os = "windows", target_os = "linux", target_os = "macos"))]
crate::install_registration::notify_after_server_registration();
```

- [ ] **Step 5: Verify tests and async safety**

Run:

```bash
cargo fmt -- --check
cargo test --lib install_registration -- --test-threads=1
rg -n "Runtime::new|block_on|thread::sleep" src/install_registration.rs
```

Expected: formatting and tests pass; the final search has no matches.

- [ ] **Step 6: Checkpoint**

Commit only if explicitly authorized:

```bash
git add src/install_registration.rs src/rendezvous_mediator.rs
git commit -m "feat(client): notify after server registration"
```

---

### Task 3: Google Apps Script Validation and Deduplication

**Files:**
- Create: `deploy/google-apps-script/RegistrationCore.gs`
- Create: `deploy/google-apps-script/Code.gs`
- Create: `tests/apps-script-registration.test.cjs`

**Interfaces:**
- Script properties: `SHEET_ID`, `RECIPIENT_EMAIL`, `CLIENT_TOKEN`
- Sheet tab: `Registrations`
- Columns: installation ID, RustDesk ID, hostname, OS, app version,
  registered UTC, received UTC, email status, email error.

- [ ] **Step 1: Add failing pure validation tests**

Create `tests/apps-script-registration.test.cjs` using `node:test`, `assert`,
and `vm`. Load `RegistrationCore.gs` into a VM context and assert:

```javascript
const validPayload = () => ({
  token: "token",
  installation_id: "3d9d36e2-70c1-4c1d-a63d-cf45f314e922",
  rustdesk_id: "123456789",
  hostname: "front-desk",
  os: "windows",
  app_version: "1.4.9",
  registered_at: "2026-07-19T12:00:00Z",
});

test("accepts the approved schema", () => {
  const result = validateRegistration(validPayload(), "token");
  assert.equal(result.ok, true);
});

test("rejects invalid token and unapproved fields", () => {
  assert.equal(validateRegistration({ token: "wrong" }, "token").ok, false);
  const payload = validPayload();
  payload.public_ip = "203.0.113.1";
  assert.equal(validateRegistration(payload, "token").ok, false);
});
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
node --test tests/apps-script-registration.test.cjs
```

Expected: FAIL because `RegistrationCore.gs` does not exist.

- [ ] **Step 3: Implement pure validation**

Create `RegistrationCore.gs` with:

```javascript
const REGISTRATION_FIELDS = [
  "installation_id",
  "rustdesk_id",
  "hostname",
  "os",
  "app_version",
  "registered_at",
];

function validateRegistration(input, expectedToken) {
  if (!input || input.token !== expectedToken) {
    return { ok: false, error: "unauthorized" };
  }
  const allowed = new Set(["token"].concat(REGISTRATION_FIELDS));
  if (Object.keys(input).some((key) => !allowed.has(key))) {
    return { ok: false, error: "unexpected_field" };
  }
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!uuid.test(String(input.installation_id || ""))) {
    return { ok: false, error: "invalid_installation_id" };
  }
  for (const field of REGISTRATION_FIELDS.slice(1)) {
    const value = String(input[field] || "");
    if (!value || value.length > 255) {
      return { ok: false, error: "invalid_" + field };
    }
  }
  if (!["windows", "linux", "macos"].includes(input.os)) {
    return { ok: false, error: "invalid_os" };
  }
  if (Number.isNaN(Date.parse(input.registered_at))) {
    return { ok: false, error: "invalid_registered_at" };
  }
  const cleaned = {};
  REGISTRATION_FIELDS.forEach((field) => cleaned[field] = String(input[field]));
  return { ok: true, value: cleaned };
}
```

- [ ] **Step 4: Implement Apps Script persistence**

Create `Code.gs` with these functions:

```javascript
const SHEET_NAME = "Registrations";
const HEADERS = [
  "installation_id", "rustdesk_id", "hostname", "os", "app_version",
  "registered_at_utc", "received_at_utc", "email_status", "email_error"
];

function jsonResponse(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const properties = PropertiesService.getScriptProperties();
    const result = validateRegistration(
      JSON.parse((e.postData && e.postData.contents) || "{}"),
      properties.getProperty("CLIENT_TOKEN")
    );
    if (!result.ok) return jsonResponse({ accepted: false, error: result.error });
    return jsonResponse(recordRegistration_(result.value, properties));
  } catch (error) {
    console.error(String(error));
    return jsonResponse({ accepted: false, error: "internal_error" });
  }
}

function recordRegistration_(data, properties) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
    if (findInstallationRow_(sheet, data.installation_id)) {
      return { accepted: true, duplicate: true };
    }
    sheet.appendRow([
      data.installation_id, data.rustdesk_id, data.hostname, data.os,
      data.app_version, data.registered_at, new Date().toISOString(),
      "email_pending", ""
    ]);
    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
  deliverEmail_(data, properties);
  return { accepted: true, duplicate: false };
}
```

Add:

```javascript
function getRegistrationSheet_(sheetId) {
  if (!sheetId) throw new Error("missing_sheet_id");
  const spreadsheet = SpreadsheetApp.openById(sheetId);
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = spreadsheet.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function findInstallationRow_(sheet, installationId) {
  if (sheet.getLastRow() < 2) return 0;
  const match = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1)
    .createTextFinder(installationId)
    .matchEntireCell(true)
    .findNext();
  return match ? match.getRow() : 0;
}

function deliverEmail_(data, properties) {
  const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
  const row = findInstallationRow_(sheet, data.installation_id);
  if (!row) throw new Error("registration_row_missing");
  const recipient = properties.getProperty("RECIPIENT_EMAIL");
  if (!recipient) throw new Error("recipient_missing");
  const body = [
    "A new Sasthotech Remote client registered.",
    "",
    "RustDesk ID: " + data.rustdesk_id,
    "Computer: " + data.hostname,
    "OS: " + data.os,
    "App version: " + data.app_version,
    "Registered (UTC): " + data.registered_at,
    "Installation ID: " + data.installation_id,
  ].join("\n");
  try {
    MailApp.sendEmail(
      recipient,
      "New Sasthotech Remote client: " + data.rustdesk_id,
      body
    );
    sheet.getRange(row, 8, 1, 2).setValues([["email_sent", ""]]);
  } catch (error) {
    sheet.getRange(row, 8, 1, 2).setValues([
      ["email_failed", String(error).slice(0, 500)]
    ]);
  }
}

function retryFailedEmails() {
  const properties = PropertiesService.getScriptProperties();
  const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
  if (sheet.getLastRow() < 2) return;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, HEADERS.length)
    .getValues();
  rows.forEach((row) => {
    if (row[7] !== "email_failed") return;
    deliverEmail_({
      installation_id: String(row[0]),
      rustdesk_id: String(row[1]),
      hostname: String(row[2]),
      os: String(row[3]),
      app_version: String(row[4]),
      registered_at: String(row[5]),
    }, properties);
  });
}
```

Do not automatically retry rows left `email_pending` by an unknown process
termination: MailApp has no idempotency key, so doing so could duplicate an
email that was delivered immediately before termination. Sheet deduplication is
strong; email delivery is best-effort and normally once, not transactionally
exactly once.

- [ ] **Step 5: Complete and run Apps Script tests**

Mock `LockService`, `SpreadsheetApp`, `PropertiesService`, `ContentService`, and
`MailApp`. Cover valid new event, duplicate UUID, invalid token, malformed JSON,
unexpected field, concurrent duplicate, successful email, and caught email
failure.

Run:

```bash
node --test tests/apps-script-registration.test.cjs
```

Expected: all tests pass.

- [ ] **Step 6: Checkpoint**

Commit only if explicitly authorized:

```bash
git add deploy/google-apps-script tests/apps-script-registration.test.cjs
git commit -m "feat(ops): add client registration webhook"
```

---

### Task 4: Build-Time Configuration and Deployment Guide

**Files:**
- Modify: `.github/workflows/flutter-build.yml`
- Create: `deploy/google-apps-script/README.md`
- Modify: `.gitignore`

**Interfaces:**
- GitHub Actions secrets:
  - `SASTHOTECH_REGISTRATION_URL`
  - `SASTHOTECH_REGISTRATION_TOKEN`
- Apps Script deployment executes as the Sheet owner and is accessible to
  anyone with the web-app URL; payload token validation remains mandatory.

- [ ] **Step 1: Add compile-time environment variables**

At workflow job level for Windows Flutter, macOS, and Linux Flutter builds, add:

```yaml
env:
  SASTHOTECH_REGISTRATION_URL: ${{ secrets.SASTHOTECH_REGISTRATION_URL }}
  SASTHOTECH_REGISTRATION_TOKEN: ${{ secrets.SASTHOTECH_REGISTRATION_TOKEN }}
```

Do not echo either value. Add a non-secret validation step:

```yaml
- name: Validate registration webhook configuration
  shell: bash
  run: |
    test -n "$SASTHOTECH_REGISTRATION_URL"
    test -n "$SASTHOTECH_REGISTRATION_TOKEN"
    case "$SASTHOTECH_REGISTRATION_URL" in https://*) ;; *) exit 1 ;; esac
```

Limit this strict validation to the `sasthotech-desktop` profile so upstream
full builds can still compile with notification disabled.

- [ ] **Step 2: Write exact Google deployment instructions**

Document:

1. Create a Google Sheet and copy its ID from the URL.
2. Open Extensions → Apps Script.
3. Add `RegistrationCore.gs` and `Code.gs`.
4. In Project Settings → Script properties set:
   - `SHEET_ID`
   - `RECIPIENT_EMAIL=shihabsararrafid@gmail.com`
   - `CLIENT_TOKEN` to at least 32 random bytes.
5. Deploy as Web app:
   - Execute as: **Me**
   - Who has access: **Anyone**
6. Copy the `/exec` URL.
7. Add the URL and token as the two GitHub repository secrets.
8. Create a time trigger for `retryFailedEmails` every 15 minutes.
9. Never place Sheet ID, recipient, token, or deployment URL in committed
   source.

Generate the token locally:

```bash
openssl rand -base64 32
```

- [ ] **Step 3: Ignore visual-design scratch files**

Add:

```gitignore
.superpowers/
```

This prevents browser brainstorming artifacts from entering commits.

- [ ] **Step 4: Verify secret hygiene**

Run:

```bash
rg -n 'shihabsararrafid@gmail\.com|SASTHOTECH_REGISTRATION_(URL|TOKEN)' \
  --glob '!docs/**' --glob '!deploy/google-apps-script/README.md' .
git diff --check
```

Expected: the email appears only in deployment documentation; source contains
environment-variable names but no URL or token value.

- [ ] **Step 5: Checkpoint**

Commit only if explicitly authorized:

```bash
git add .github/workflows/flutter-build.yml \
  deploy/google-apps-script/README.md .gitignore
git commit -m "ci: inject private registration webhook config"
```

---

### Task 5: End-to-End Verification

**Files:**
- Verify all files from Tasks 1–4.

- [ ] **Step 1: Run local tests and formatting**

Run:

```bash
cargo fmt -- --check
cargo test --lib install_registration -- --test-threads=1
node --test tests/apps-script-registration.test.cjs
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Deploy Apps Script and perform a direct webhook smoke test**

Use temporary shell variables so credentials do not enter history:

```bash
read -r -s WEBHOOK_TOKEN
read -r WEBHOOK_URL
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data "{\"token\":\"$WEBHOOK_TOKEN\",\"installation_id\":\"$(uuidgen | tr '[:upper:]' '[:lower:]')\",\"rustdesk_id\":\"smoke-test\",\"hostname\":\"manual-test\",\"os\":\"macos\",\"app_version\":\"1.4.9\",\"registered_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
  "$WEBHOOK_URL"
```

Expected: `{"accepted":true,"duplicate":false}`, one sheet row, and one email.

- [ ] **Step 3: Build a configured desktop client**

Trigger the Sasthotech desktop workflow after secrets are configured. Verify
the build logs never print either secret.

- [ ] **Step 4: Fresh-install registration smoke test**

On a test machine with no previous Sasthotech Remote config:

1. Install and launch the client.
2. Confirm it registers with the Sasthotech RustDesk server.
3. Confirm one Google Sheet row contains the approved fields.
4. Confirm one email reaches `shihabsararrafid@gmail.com`.
5. Restart the client and confirm no second row or email appears.

- [ ] **Step 5: Failure-isolation smoke test**

Temporarily disable the Apps Script deployment, then use a fresh test install.
Confirm:

- Client startup remains responsive.
- Server registration succeeds.
- Remote access works.
- Logs show a categorized webhook failure without token content.
- Re-enabling Apps Script and restarting produces the missing row/email.

- [ ] **Step 6: Final security and repository check**

Run:

```bash
git status --short --branch
git diff --check
rg -n 'Sasthotech2025' . || true
```

Expected: no plaintext permanent password. Report that the existing shared
password hash must be rotated before production distribution.
