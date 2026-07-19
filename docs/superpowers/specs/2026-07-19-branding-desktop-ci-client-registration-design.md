# Sasthotech Branding, Desktop CI, and Client Registration Design

Date: 2026-07-19
Status: Approved in conversation

## Context

The custom RustDesk client already presets Sasthotech's ID server, relay server,
public key, permanent password, and application display name. This phase
completes visible desktop branding, adds a focused desktop build workflow, and
records each newly installed client after its first successful registration
with the Sasthotech RustDesk server.

## Confirmed requirements

1. Product name: **Sasthotech Remote**.
2. Use the complete supplied Sasthotech logo, including its tagline, for the
   Windows, macOS, and Linux app icons despite reduced legibility at small
   sizes.
3. Use a small monochrome healthcare mark for the macOS status-bar icon because
   macOS template icons cannot display the full horizontal color logo
   effectively.
4. Add a manually triggered desktop-only GitHub Actions workflow for:
   - Windows x64
   - Linux x64
   - macOS Intel
   - macOS Apple Silicon
5. After the first successful RustDesk-server registration, record one event in
   Google Sheets and normally send one email to `shihabsararrafid@gmail.com`.
6. Record installation UUID, RustDesk ID, hostname, OS, app version, and UTC
   timestamp. Do not collect public IP, local username, or hardware details.
7. Notification failure must never delay or prevent RustDesk startup, server
   registration, or remote access.

## Branding design

The supplied file
`/Users/shihabsararislamrafid/Downloads/Untitled design.png` is the input asset.
Implementation copies it into a tracked branding-assets directory so builds do
not depend on a developer's Downloads folder.

The source image is cropped to remove excess whitespace and placed on a square
white canvas without distorting its aspect ratio. Platform assets are generated
from that canonical file:

- Windows multi-resolution `.ico`
- macOS `AppIcon.appiconset` PNG sizes
- Linux application and package PNG sizes
- macOS monochrome template tray image

Visible product metadata uses **Sasthotech Remote** in window titles, Finder and
Dock, Start menu, Linux launchers, and installer presentation. Package and
artifact names use the filesystem-safe slug `sasthotech-remote`.

Internal executable names, URI schemes, service identifiers, bundle IDs, and
package IDs remain unchanged where renaming them would risk breaking existing
RustDesk protocol, service, packaging, or upgrade behavior. The macOS build
script is updated to package the actual `Sasthotech Remote.app` bundle rather
than relying on a hardcoded `RustDesk.app` path.

## Desktop-only CI design

A new manually triggered workflow named **Sasthotech Desktop Build** invokes
only the four confirmed desktop targets. It reuses existing build logic where
practical and adds target selection rather than duplicating the full upstream
workflow.

Each target validates that its expected installer was produced and then uploads
it as a GitHub Actions artifact. Artifact upload does not depend on GitHub
Release publishing. Release publishing remains optional and non-fatal so a
release outage cannot hide an otherwise successful installer.

The existing upstream nightly, tag, and full CI workflows remain available.

## Client registration architecture

### Registration trigger

The rendezvous mediator provides authoritative client-side confirmation:

- `RegisterPeerResponse` without a public-key request confirms an already
  registered client is online.
- `RegisterPkResponse::OK` confirms a newly registered key.

Either successful response starts a background registration-notification task.
An in-process guard prevents concurrent duplicate attempts.

### Persistent state

The client generates a random installation UUID and stores it in RustDesk's
local configuration. It also stores a completion flag only after the webhook
returns a valid success response.

The installation UUID, rather than RustDesk ID alone, is the deduplication key.
A normal restart therefore produces no new event, while a genuinely fresh
installation with cleared local state can produce a new event.

### Payload

The client sends JSON over HTTPS:

```json
{
  "token": "build-injected validation token",
  "installation_id": "random UUID",
  "rustdesk_id": "client ID",
  "hostname": "computer name",
  "os": "windows|linux|macos",
  "app_version": "version",
  "registered_at": "UTC ISO-8601 timestamp"
}
```

The notification request runs in an existing Tokio runtime and never blocks the
rendezvous loop. Network and service errors are logged without exposing tokens.
Failures leave the completion flag unset so a later successful server
registration can retry. Retries are bounded within each process and naturally
resume on a later launch.

## Google Apps Script design

A standalone Apps Script web app receives the registration POST. Deployment
properties—not source code—hold:

- Google Sheet ID
- destination email address
- client validation token

The script:

1. Rejects missing/invalid tokens and malformed or oversized payloads.
2. Validates all required fields and caps field lengths.
3. Uses `LockService` to serialize deduplication and row insertion.
4. Checks the installation UUID against the dedicated registrations sheet.
5. Appends one row when the installation UUID is new.
6. Sends one notification email.
7. Returns success for both a newly recorded event and an existing UUID so
   client retries stop safely.

Apps Script web apps do not expose arbitrary request headers to `doPost`, so the
client validation token is carried in the JSON body and is removed before the
row is written. The email and Google Sheets credentials never enter the client
or repository. The Apps Script URL and client token are compiled into private
builds using GitHub Actions secrets. Because any compiled client value can be
extracted, the token is an anti-spam control rather than strong device
authentication.

Email failure after row insertion is recorded in the sheet and can be retried
by a scheduled Apps Script function without adding another client row. The
function sends only rows explicitly marked `email_failed`; it does not retry an
ambiguous `email_pending` row after an unknown process termination because
MailApp has no idempotency key. Sheet insertion is exactly deduplicated; email
delivery is best-effort and normally once, not transactionally exactly once.
The client considers the event accepted once the durable row exists.

## Error handling

- RustDesk operation continues normally when registration notification is
  disabled, misconfigured, offline, timed out, rate-limited, or rejected.
- HTTP calls use strict connect and total timeouts.
- Logs contain status and error categories but never the validation token.
- Duplicate client requests are idempotent.
- Apps Script uses a lock and durable sheet row to avoid duplicate email during
  concurrent retries.
- Missing CI secrets disable registration notification explicitly; they do not
  produce a build containing placeholder credentials.

## Testing

### Rust

- Payload contains the confirmed fields and excludes public IP and username.
- Installation UUID persists across launches.
- Completion state is written only after a valid success response.
- Duplicate in-process triggers create one request.
- Timeout, HTTP failure, and malformed responses leave RustDesk operational and
  eligible for a later retry.
- Both successful rendezvous response paths trigger the task.

### Apps Script

- Valid new payload creates one row and one email.
- Duplicate installation UUID creates neither a second row nor a second email.
- Invalid token, malformed JSON, missing fields, oversized values, and invalid
  UUID are rejected.
- Concurrent duplicate requests remain idempotent.
- Email failure leaves a durable row and an explicit delivery status.
- Scheduled email retry processes failed rows without duplicating sheet rows.

### CI and manual smoke testing

- Workflow syntax and target selection are validated.
- All four confirmed installers are uploaded as artifacts.
- Fresh installs show the selected name and platform icons.
- macOS packaging finds `Sasthotech Remote.app`.
- A fresh client produces one row and one email after server registration.
- Restarting the client produces no duplicate.
- Remote access works while Apps Script is unavailable.

## Deployment sequence

1. Add and generate branding assets.
2. Add and validate the focused desktop workflow.
3. Create the Google Sheet and deploy the Apps Script under the user's Google
   account.
4. Add the deployment URL and generated validation token as private GitHub
   Actions secrets.
5. Enable the client notifier and build test installers.
6. Perform fresh-install smoke tests on Windows, Linux, Intel macOS, and Apple
   Silicon macOS.
7. Rotate the shared permanent-access password and webhook token before
   production distribution.

## Non-goals

- Android and iOS branding/build changes
- Public-IP collection
- User activity monitoring
- Hardware inventory
- Strong hardware-backed client attestation
- Replacing the RustDesk server or protocol
- Code signing and Apple notarization in this phase
