# Employee Management Acceptance

## Implemented Scope

- Management API: employee/admin login, revocation, shared directory, CSV,
  employee-app-reported audits, company defaults and employee policy overrides.
- Same-origin browser console: Clients, Sessions, Employees, Policies; employee
  role sees only shared directory and its own reports.
- Employee desktop source integration: existing account login, company-directory
  tab, original connection tab, common Rust outbound authorization, real login
  success callbacks, heartbeat and bounded telemetry retry.
- Official hbbs/hbbr and customer protocol remain unchanged. Ordinary customer
  builds do not require the management service.

## Build Selection

Use **Sasthotech Desktop Build** with `employee-mode=true` and a management HTTPS
origin such as `https://management.example.com`. Customer builds use false.
Native build variables are `SASTHOTECH_EMPLOYEE_MODE=1` and
`SASTHOTECH_EMPLOYEE_API=https://management.example.com`. No employee credential
is compiled into either build. The origin cannot contain a path, query, password
or fragment. Build validation rejects a missing HTTPS URL; runtime validates
the complete origin before authorization.

Managed mode preserves the exact normalized native target, including direct IP,
domain/port and alternate-server syntax. Target validation reuses RustDesk's
untrusted-peer-ID validation; the management API records the same value rather
than stripping a suffix and falsely identifying another target. Actual network
compatibility for those connection types still requires the matrix below.

## Local Verification

- Python API regression tests: `PYTHONPATH=management python -m pytest management/tests -q`.
- Browser smoke: `node management/tests/browser_smoke.cjs` with Playwright and
  Python available; set `PLAYWRIGHT_MODULE`, `MANAGEMENT_TEST_PYTHON`, and
  `CHROMIUM_EXECUTABLE` when using isolated local tooling.
- Container smoke: build `management/`, then run its `python smoke.py` command
  in a disposable non-root, read-only container.
- Recovery: `sh management/deploy/backup.sh DB NEW_BACKUP_DIRECTORY`, then
  `sh management/deploy/restore-check.sh BACKUP_DIRECTORY NEW_TEST_DIRECTORY`.
  Never point the verification command at an existing directory.
- Native tests to run where toolchains exist: `cargo test --lib employee_management`,
  desktop Rust compile, `flutter analyze` and
  `flutter test test/employee_management_model_test.dart` from `flutter/`.

## Installed-Client Matrix

Every row below is pending real installed-client verification. Source changes,
API tests and browser tests do not prove remote-session behavior.

| Employee OS | Customer OS | Password/approval | Control/audio | Clipboard | File transfer | Camera/terminal | Tunnel/RDP | Reconnect/audit |
|---|---|---|---|---|---|---|---|---|
| Windows x64 | Windows unchanged | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| macOS ARM64 | Windows unchanged | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| macOS Intel | macOS unchanged | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Linux x64 | Linux unchanged | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

Verify signed-out deep links, recent peers, secondary windows and direct Rust
entry cannot initiate managed connections. Moving a display to another window
must not duplicate audits. Verify revocation blocks subsequent connections,
service outages block new attempts but not established sessions, and process
termination produces interrupted rather than falsely completed reports.

## Deployment Boundary

No live VPS deployment, DNS change, certificate issuance, native build or
installed-client matrix has been performed in this workspace. Deployment needs
the management hostname, authorized VPS access, reviewed HTTPS configuration,
and a backup/restore rehearsal against the deployment volume. Keep the existing
hbbs/hbbr identity keys and data separate from the management database.

Restrictions and telemetry apply to the managed employee application only.
Someone using an ordinary RustDesk client and valid customer credentials can
bypass this application. Audit records are not server-attested or recordings
of every action performed on the remote computer.
