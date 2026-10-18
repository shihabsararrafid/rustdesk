# Employee Client And Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing management API to the employee desktop client, add administrator screens, and provide deployment and compatibility verification artifacts without replacing customer installations.

**Architecture:** Keep official hbbs/hbbr and the RustDesk protocol unchanged. Add a separately built managed-employee mode with HTTPS authorization and audit lifecycle tracking in Rust, reuse Flutter login and peer components, and serve a same-origin browser console from the management API. The ordinary customer build remains operational without a management service.

**Tech Stack:** Existing Rust/Tokio/reqwest/serde and Flutter; existing Python/FastAPI/SQLite management service; server-served HTML/CSS/JavaScript console with no additional frontend framework. Use existing Flutter icons and Lucide icons in the browser console through a pinned local asset.

**Spec:** `docs/superpowers/specs/2026-10-14-employee-management-design.md`

## Global Constraints

- Every employee sees the entire shared directory; no assignments.
- Keep existing connection features and remote-client protocol compatibility.
- Managed-mode login is an employee-app gate, not fleet-wide enforcement.
- Unchanged ordinary clients and known passwords can bypass employee-app auditing.
- Never ship employee credentials or API bearer tokens as build constants.
- Unknown presence stays unknown until an OSS-compatible live query is verified.
- New managed sessions fail closed if API authorization is unavailable; established remote sessions survive telemetry outages.
- Do not commit, push, deploy, change DNS, or alter the live hbbs/hbbr data directory.

## Review Focus

1. Deep links, secondary windows, recent peers and reconnects must not bypass managed authorization (Tasks 3, 4).
2. Tokens and session identity must not leak through URL arguments, logs or inter-window messages (Tasks 2, 4).
3. UI connection indication is not proof of authentication; audit success comes from Rust's accepted login/peer-info path (Task 3).
4. Clipboard/file-transfer restrictions must be described as employee-app restrictions, never enforcement on unchanged customer clients (Tasks 1, 3, 4).
5. A disconnect, application crash, lost telemetry or account revocation must not produce invented clean audit outcomes (Tasks 2, 3).

## File Boundaries

Backend additions: `management/app/policies.py`, `management/app/console.py`,
`management/app/migrations/002_employee_policies.sql`,
`management/static/index.html`, `management/static/console.js`,
`management/static/console.css`, `management/static/vendor/lucide.js`,
`management/tests/test_policies.py`, `management/tests/test_console.py`.

Rust additions: `src/employee_management.rs`,
`src/employee_management/{api,audit,policy}.rs`; modify only required sites in
`src/lib.rs`, `src/flutter.rs`, `src/flutter_ffi.rs`, `src/client.rs`,
`src/ui_session_interface.rs`, and `src/preset_config.rs`.

Flutter additions: `flutter/lib/models/employee_management_model.dart`,
`flutter/lib/desktop/widgets/employee_directory.dart`, and corresponding
`flutter/test/employee_management_*_test.dart`; extend existing desktop home and
account surfaces rather than replacing the remote session screens.

Deployment additions: `management/deploy/nginx.conf.example`,
`management/deploy/backup.sh`, `management/deploy/restore-check.sh`, and
`docs/employee-management-acceptance.md`; extend
`.github/workflows/sasthotech-desktop.yml` and management README.

## Task 1: Authenticated Session Authorization And Policies

- [ ] Add failing API tests for effective policy, admin-only policy mutation,
  disabled employee access, supported connection modes, and policy violations.
  Run `PYTHONPATH=management python -m pytest management/tests/test_policies.py -q`.
- [ ] Define policy fields `allow_remote_control`, `allow_file_transfer`,
  `allow_clipboard`, `allow_tcp_tunnel`, `allow_terminal`, `allow_camera` as
  booleans, default true. Maintain company defaults plus employee overrides.
  These controls are explicitly scoped to the managed application.
- [ ] Add a transactional version-2 migration preserving version-1 accounts,
  tokens, clients and audit history. Fail safely on a newer schema. Test actual
  version-1 database upgrade and transaction rollback.
- [ ] Add `GET /api/management/me` returning authenticated identity and effective
  policy; admin `PUT /api/management/policies/company` and
  `PUT /api/management/policies/employees/{employee_id}` accept only these fields.
  Extend session creation to snapshot policy and reject prohibited modes.
- [ ] Keep directory visibility independent from policy. Allow starting a
  session to a valid numeric ID not yet in the directory by atomically creating
  a minimal auto-discovered entry labelled with its ID; employees cannot attach
  arbitrary customer metadata. Preserve direct-ID connection functionality.
- [ ] Verify rejected authorization creates no falsely successful audit event,
  and existing directory/report APIs still pass their regression tests.

## Task 2: Rust Management API And Audit Transport

- [ ] Add tests using a local mock HTTP server for authorization, token expiry,
  timeout, 401, malformed JSON, HTTP redirects, and retry/idempotency behavior.
- [ ] Define `ManagementConfig { enabled: bool, api_url: String }` from immutable
  employee-build configuration. Enabled builds require a valid HTTPS origin;
  debug builds may explicitly permit loopback HTTP for integration tests.
- [ ] Implement typed API request/response structs, including
  `authorize_session(target_id, mode, request_id) -> Result<AuthorizedSession>`;
  `AuthorizedSession` carries audit UUID, actor ID, target ID and policy.
  Use the existing account bearer token without passing it through URLs.
- [ ] Use bounded connect/request timeouts, strict HTTPS, same-origin redirects
  only (or disable redirects), no credentials in logs, and no locks across await.
  Reuse the existing runtime; do not create a runtime per request.
- [ ] Implement `SessionAudit` with stable event UUIDs, a bounded in-memory retry
  queue, explicit authenticated/failed/closed outcomes and 30-second heartbeat.
  Retry uncertain requests with the same event UUID, and mark unrecoverable gaps.
  Do not persist raw tokens in an audit queue.
- [ ] Test outage after connection keeps the remote connection alive while
  backend reports unknown/interrupted telemetry. A new connection must fail
  when authorization cannot be obtained.

## Task 3: Common Rust Session Gate And Real Lifecycle

- [ ] Trace and document all callers of `session_add`, `session_start_`,
  `Client::start` and reconnection paths before choosing the common gate. Add
  tests proving direct Rust entry cannot bypass authorization in managed mode.
- [ ] Integrate the asynchronous gate at the common outbound I/O start path,
  before any rendezvous/relay/direct-peer connection. Never perform synchronous
  HTTP inside `session_add_sync`, and do not treat UI gating as enforcement.
- [ ] Bind an authorization result to actor, target, local session and mode;
  reject reuse for another target/mode. Additional display windows sharing one
  underlying connection must not create duplicate audit sessions.
- [ ] Emit authenticated only on successful protocol login/accepted peer-info,
  not socket creation. Map camera, file transfer, tunnel/RDP and terminal paths
  to distinct audit modes; extend backend enums rather than silently dropping
  these modes.
- [ ] Emit failed for pre-auth denial/timeout; close after authenticated network
  termination. Instrument the underlying I/O lifetime, not only Flutter's
  window-close handler. Reconnects receive separate attempt IDs linked to the
  previous attempt; changing employee requires new authorization.
- [ ] Enforce managed-app mode and clipboard/file-transfer controls at outbound
  request/send paths, not just hidden buttons. Leave ordinary customer builds
  and incoming-session behavior unchanged. Do not claim malicious-build resistance.
- [ ] Run Rust unit tests and desktop compile checks; report missing toolchains
  explicitly rather than labeling static checks as a passing build.

## Task 4: Employee Login And Shared Directory UI

- [ ] Add Flutter tests for signed-out state, expired token, loading/error/retry,
  all-client visibility, pagination, unknown presence and denied connection mode.
- [ ] Reuse the existing `/api/login` account flow and retain access to Settings
  and normal RustDesk features. In the employee build, prevent new outbound
  connections while signed out and show the login action.
- [ ] Add the common client directory to desktop home using existing peer/list
  components, search and pagination. Keep manually entered IDs and recent peers
  usable through the same Rust gate. Never show a fabricated green online dot.
- [ ] Query `/api/management/me` for policy display. UI disables disallowed
  commands with a reason; Rust remains authoritative for this application.
- [ ] Trace CLI/URI/window-manager entry and pass target/mode only; no bearer
  tokens in process arguments. Secondary windows load identity through existing
  secure account state and cannot silently inherit another user's audit.
- [ ] Run Flutter analysis/widget tests. Smoke-test ordinary customer build
  while management service is offline and managed employee build while signed out.

## Task 5: Same-Origin Management Console

- [ ] Add backend tests for console routes, static asset delivery, no-store
  responses and absence of hardcoded credentials. Add browser tests for login,
  employee/admin role differences, revocation and API error states.
- [ ] Serve `/console` and local static assets from FastAPI. Use the same bearer
  APIs; keep token in page memory only. Reload requires login. Do not embed a
  token in HTML, URL, localStorage or external analytics.
- [ ] Build compact navigation for Clients, Sessions and Employees. Employees
  can read the shared directory and their own reports; administrators can manage
  employees, passwords, client entries, CSV import/export and policies.
- [ ] Reports include employee, target, mode, UTC start/end, state, outcome and
  telemetry gaps, and state explicitly that logs are employee-app-reported.
  Include date/employee/client filters, pagination and empty/error/loading states.
- [ ] Use DOM textContent for user-controlled values, never HTML interpolation;
  add CSP, same-origin assets and no remote CDN dependency. Destructive actions
  require confirmation and handle 401/403/409 without losing unrelated edits.
- [ ] Verify browser workflows and screenshots on desktop/mobile viewports.
  Do not count OpenAPI docs as the administrator interface.

## Task 6: Deployable Packaging And Compatibility Gates

- [ ] Add build inputs for employee versus ordinary customer mode and management
  URL; preserve existing defaults when employee mode is off. Never include API
  credentials as build inputs. Test missing/invalid employee URL fails the build.
- [ ] Add TLS reverse-proxy example with bounded body/request timeouts, persistent
  loopback management Compose, health checks and automatic restart. Preserve the
  user's working hbbs/hbbr Compose and identity keys.
- [ ] Add fail-safe backup/restore scripts requiring explicit target paths and
  rejecting production-volume overwrite by default. Exercise a disposable-volume
  restore and compare users, directory and audit records before/after.
- [ ] Extend Docker smoke to cover both employee roles, policy denial,
  administrator console delivery, migration and restart. Run all management,
  existing registration, Rust, Flutter and browser suites; enumerate any skips.
- [ ] Prepare an acceptance matrix for Windows/Linux/macOS employee builds
  connecting to unchanged customer clients: remote control, clipboard, file
  transfer, audio, camera, tunnel/RDP, terminal and approval/password login.
  Record actual tested platform/version and unavailable hardware separately.
- [ ] End with local software plus test evidence. Live VPS deployment requires
  the user's management hostname and authorized server-access mechanism. Do not
  invent SSH credentials, change DNS or label the VPS deployed without proof.

## Self-Review And Handoff

The existing approved spec covers these components. This plan expands the
foundation-only plan's explicitly deferred work. Native execution in this
session is retained. All six tasks require independent regression evidence;
test fixtures must cover each named failure mode before production code changes.
Runtime/installed-client checks that cannot be run remain unverified, not passed.
No production implementation changes are made by writing this plan.

## Execution Record (2026-10-18)

- [x] Added version-2 migration, company/employee policies, effective policy,
  policy-bound session creation and exact-target automatic directory entries.
- [x] Implemented Rust employee-mode authorization and audit transport in source.
  Ordinary builds leave employee mode disabled. Rust syntax parsing passed;
  native compilation and mock-HTTP Rust tests remain unverified.
- [x] Wired the common connection-start path, accepted protocol login,
  clipboard/file-action gates, disconnect handling and joined tunnel shutdown
  in source. Actual remote-session lifecycle remains a native acceptance gate.
- [x] Added Flutter directory/model, existing account-login reuse and model tests;
  retained the original connection surface in a second tab. Flutter SDK is not
  installed, so analysis, tests and runtime layout remain unverified.
- [x] Added same-origin console and exercised real browser admin login,
  client/employee creation, policy changes and switching, employee role isolation,
  shared directory, empty reports and desktop/mobile layout.
- [x] Added employee/customer build inputs, deployment TLS example, consistent
  SQLite backup and non-destructive restore verification. Live VPS deployment
  and the installed-client OS matrix remain blocked on deployment details and
  native/hardware access, not marked complete.

Verification: 27 management tests passed; existing/source-contract Python suite
ran 36 tests with 26 passed and 10 skipped; Apps Script Node suite 17 passed.
Rust syntax parser accepted the changed Rust sources (not type checking).
Workflow/Compose YAML validation, JS syntax checking, Docker build, non-root
read-only container HTTP smoke and backup/restore tests passed. Local
`/console` returned HTTP 200 and `/readyz` reported ready after restart.

Independent review found an outbound clipboard bypass, tunnel-runtime shutdown
losing audit events, lost-authentication telemetry semantics, stale policy-form
cache and a Flutter button-width overflow. Source fixes include direct clipboard
checks, inner and outer task joining, rejecting heartbeat/closure before auth,
stopping telemetry when auth-event delivery is exhausted, cache refresh and
96-pixel action width. API and browser regressions were rerun. Native runtime
proof of the Rust/Flutter fixes remains outstanding.

Ruling: retain the approved native implementation method rather than dispatching
implementation agents; one independent read-only reviewer was used. Ruling:
keep the small Rust transport/policy implementation in one module rather than
three submodules to avoid unnecessary abstraction; split when justified by
growth. Ruling: extend authorization beyond numeric IDs using existing RustDesk
target validation, because refusing direct/alternate-server targets would violate
the compatibility requirement; cost is broader validation coverage and a pending
real-network compatibility matrix. Ruling: declare unavailable native checks
explicitly instead of installing a full Rust/Flutter/vcpkg toolchain or claiming
API tests prove desktop behavior.

No commits, pushes, DNS changes or live RustDesk-server changes were made.
See `docs/employee-management-acceptance.md` for the release gates and commands.
