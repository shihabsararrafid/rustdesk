# Employee Management Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a locally testable management API for employee accounts, a company-wide customer directory, and employee-app-reported session records.

**Architecture:** Add an independent service alongside official hbbs/hbbr without changing their protocol or customer installations. Build and test the API foundation first; connecting the employee UI and recording real sessions are separate subsequent increments, not claimed delivered by this plan.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, SQLite via standard-library sqlite3, Argon2id via argon2-cffi, pytest/httpx. A single API worker and a persistent local Docker volume are the initial deployment model; this is not a multi-replica database design.

**Spec:** `docs/superpowers/specs/2026-10-14-employee-management-design.md`

## Global Constraints

- Every active employee sees all directory entries; no customer assignments.
- Existing hbbs/hbbr, customer clients, and RustDesk protocol remain unchanged.
- Do not store remote-access passwords, clipboard contents, or file contents.
- Audit records are employee-application-reported, not server-attested.
- Directory membership must not be presented as online status.
- Do not deploy, commit, push, or change existing Git configuration.
- This foundation does not implement a new client login gate or intercept connections.

## Review Focus

1. Account disablement/password reset invalidates every existing session, not only future logins (Task 2).
2. An employee cannot forge another employee's audit identity or update their sessions (Task 4).
3. Concurrent duplicate events cannot invent multiple sessions or change terminal outcomes (Task 4).
4. CSV import/export handles duplicate IDs, malicious formulas, oversized input, and Unicode safely (Task 3).
5. Restart/crash/database contention cannot turn missing telemetry into a claimed clean disconnect (Tasks 1, 4, 5).

## Files And Boundaries

Create under `management/`:

- `pyproject.toml`: dependencies, Python floor, pytest configuration.
- `app/main.py`: application factory `create_app(settings)`, routers and lifespan.
- `app/settings.py`: validated environment configuration without embedded secrets.
- `app/database.py`: request-local connections, migration transaction, foreign keys, busy timeout, WAL.
- `app/migrations/001_initial.sql`: versioned schema.
- `app/security.py`: password hashing and token generation/digest helpers.
- `app/auth.py`: login/current-user/logout routes and authentication dependencies.
- `app/employees.py`: administrator-only employee operations.
- `app/directory.py`: common directory and CSV operations.
- `app/audit.py`: session lifecycle and report routes.
- `app/cli.py`: explicit first-admin creation from an interactive password or secret file.
- `tests/conftest.py`: isolated temporary databases and application fixtures.
- `tests/test_database.py`, `test_auth.py`, `test_employees.py`, `test_directory.py`, `test_audit.py`, `test_deployment.py`.
- `Dockerfile`, `compose.yml`, `.env.example`, `README.md`.

Use synchronous FastAPI handlers for blocking SQLite/Argon2 work, not blocking operations inside async handlers. Parameterize SQL. Set database permissions appropriately and never log credentials or authorization headers.

## Task 1: Persistent Database And Application Lifecycle

**Interfaces:** `create_app(settings: Settings) -> FastAPI`; `connect_database(path) -> sqlite3.Connection` with explicit transactions. Settings requires a database path, positive session lifetime (default eight hours), allowed HTTPS public origin, and bounded request sizes.

- [ ] Write `test_database.py`: create a temporary database, apply migrations twice, insert a user, reopen and verify persistence; verify foreign-key enforcement and rollback after an exception.
- [ ] Run `python3 -m pytest management/tests/test_database.py -q`; confirm failure before implementation.
- [ ] Implement application factory, settings, migration runner, connection cleanup, and schema:
  `users(id, username UNIQUE, password_hash, role, disabled, created_at)`;
  `auth_sessions(token_hash PRIMARY KEY, user_id REFERENCES users, expires_at, revoked_at)`;
  `clients(id, rustdesk_id UNIQUE, customer_name, device_label, notes, created_at, updated_at)`;
  `audit_sessions(id, request_id, employee_id REFERENCES users, client_id REFERENCES clients, target_id, mode, state, started_at, authenticated_at, last_seen_at, ended_at, outcome, UNIQUE(employee_id, request_id))`;
  `audit_events(session_id REFERENCES audit_sessions, event_id, kind, received_at, UNIQUE(session_id, event_id))`;
  `login_limits(key_hash PRIMARY KEY, window_started_at, attempts)`.
- [ ] Add `/healthz` liveness and `/readyz` database-readiness endpoints; no public diagnostic secrets.
- [ ] Run the tests, including two connections contending for the database with bounded timeout and explicit failure rather than silent data loss.

## Task 2: Revocable Authentication And Employee Administration

**Interfaces:** `require_user(request) -> authenticated user`; `require_admin(request) -> administrator`; role and disabled state are fetched from the database per authorized request, never trusted from a request body.

- [ ] Write auth tests for invalid passwords, unknown users, disabled users, expired/revoked tokens, wrong roles, logout, reset revocation, and persistent login throttling. Assert login errors do not distinguish unknown users from wrong passwords.
- [ ] Run `python3 -m pytest management/tests/test_auth.py management/tests/test_employees.py -q`; confirm red.
- [ ] Implement Argon2id password storage and cryptographically random opaque bearer tokens; store SHA256 token digests only. Verify password length bounds before expensive hashing. Enforce persistent per-username and source-address throttling, with trusted-proxy handling disabled by default.
- [ ] Implement `/api/login`, `/api/currentUser`, `/api/logout`, `/api/login-options` using JSON contracts read from `flutter/lib/common/hbbs/hbbs.dart`, `src/hbbs_http/account.rs`, and `flutter/lib/models/user_model.dart`. Use fixture tests derived from those contracts; support password login only, return no advertised OIDC/2FA functionality.
- [ ] Implement administrator routes `POST /api/management/employees`, `GET /api/management/employees`, `PATCH /api/management/employees/{id}`, and `POST /api/management/employees/{id}/password`. Reset/disable and token revocation occur in the same transaction. Prevent disabling the last active administrator.
- [ ] Implement `python -m app.cli create-admin --username <name> --password-file <path>`; refuse overwriting an existing username, never print passwords/tokens, and do not create default accounts on startup.
- [ ] Verify employee/admin authorization, token digest storage, and all revocation tests pass.

## Task 3: Shared Directory And Safe CSV

**Interfaces:** authenticated `GET /api/management/clients` returns `{items: [{id,rustdesk_id,customer_name,device_label,notes,presence:"unknown"}],total}` with bounded pagination. Admin-only create/update/delete/import; no assignment filter. Reject deletion of referenced clients with conflict rather than deleting audit history.

- [ ] Write tests that two employees see identical entries, employees cannot mutate entries, duplicates fail, imported customer passwords are not accepted, and online presence is always unknown.
- [ ] Write CSV tests for quoted commas, UTF-8 BOM, embedded newlines, conflicting duplicate IDs, excess rows/bytes, bad column headers, and values starting with `=`, `+`, `-`, `@`, tab, or carriage return. Failed import leaves no partial rows.
- [ ] Run `python3 -m pytest management/tests/test_directory.py -q`; confirm red.
- [ ] Implement CRUD with field bounds: RustDesk ID 1–64 ASCII digits, customer/device labels 1–200 characters, notes 0–2000 characters. Accept no remote passwords. Support numeric self-hosted IDs first; document unsupported formats explicitly.
- [ ] Implement `POST /api/management/clients/import` as UTF-8 CSV (maximum 2 MiB, 5000 rows) with exact columns `rustdesk_id,customer_name,device_label,notes`; validate the full file before a single transaction. Export the same columns through `GET /api/management/clients/export`, neutralizing spreadsheet formula prefixes.
- [ ] Verify every role sees the full directory, unknown presence, and all import/export tests pass.

## Task 4: Idempotent Session Audit And Reports

**Interfaces:** `POST /api/management/sessions` consumes `{request_id: UUID,client_id: UUID,mode: enum}` and derives identity/target from the authenticated user and directory. Modes: `remote_control`, `file_transfer`, `tcp_tunnel`, `other`. Return `{id,state,started_at}`; repeated identical requests return the original session, conflicting reuse returns 409.

`POST /api/management/sessions/{id}/events` consumes `{event_id: UUID,kind: enum,outcome?: enum}`. Kinds: `authenticated`, `heartbeat`, `failed`, `closed`. Outcomes are bounded enums, not arbitrary exception messages. Event timestamps are server-generated. Administrators can read reports but cannot impersonate event producers.

- [ ] Write tests for attempt→authenticated→closed, attempt→failed, idempotent retries, conflicting UUID reuse, foreign-employee session updates, duplicate concurrent submissions, and denied post-terminal transitions.
- [ ] Write tests where authenticated sessions stop heartbeating: report `interrupted` after 120 seconds without telemetry, retain last activity, and leave exact end time/duration unknown. Active-session telemetry from a previously authorized now-disabled account is rejected; no remote termination claim is made.
- [ ] Run `python3 -m pytest management/tests/test_audit.py -q`; confirm red.
- [ ] Implement state transitions transactionally: `attempted -> authenticated|failed|closed`; `authenticated -> closed`; heartbeat updates only nonterminal records. Exact duplicate events succeed, conflicting same event ID fails. Store server-receipt event history and prohibit modification of prior records through public routes.
- [ ] Implement admin-only `GET /api/management/reports/sessions` filtered by employee, client, state, and UTC date range, with bounded pagination and deterministic ordering. Employees may retrieve only their own session records. Include `source:"employee_app_reported"` and `presence:"unknown"` where applicable; do not imply server attestation.
- [ ] Verify database reopen preserves reports, injected employee IDs cannot override authentication, and all lifecycle tests pass.

## Task 5: Deployment And Verification Handoff

- [ ] Write tests validating Compose keeps hbbs/hbbr unchanged, management binds to `127.0.0.1:21114`, persists `/data`, runs non-root, and contains no embedded admin/password/token values.
- [ ] Run the deployment test and confirm red, then add a separate management Compose service. Document HTTPS reverse-proxy configuration and forwarding only from a trusted local proxy. Do not change the user's live Compose.
- [ ] Create a pinned dependency lock/constraints file and Docker image build with a writable dedicated data volume. Document bootstrap, backup/restore while stopped, retention, private network exposure, and upgrade/migration failure behavior. Do not enable broad CORS or allow client-selected filesystem/database paths.
- [ ] Run `python3 -m pytest management/tests -q`, then existing `python3 -m unittest discover -s tests -p 'test_*.py'` and `node --test tests/apps-script-registration.test.cjs`. Report each independently; do not treat a skipped/unavailable suite as passing.
- [ ] If Docker is running, build and start the service locally, bootstrap a temporary administrator, create two employees and a customer, submit session events, restart, and verify retained reports. Otherwise report Docker smoke verification unavailable.
- [ ] Review the diff for secrets, unrelated edits, protocol changes, authorization bypasses, request limits, and transaction boundaries. Leave all changes uncommitted for user review.

## Subsequent Plans And Stop Condition

This plan ends with the tested API and deployment artifacts. It does not produce an audited employee installer or an administration UI.

The next plan must map every employee connection entry path (main Connect,
recent peers, directory, file-transfer launch, CLI/URI, secondary windows, and
reconnection), integrate employee authentication and server-created sessions,
then connect real Rust session lifecycle callbacks. Reuse existing address-book
UI only after response-contract coverage is demonstrated; never wire a partial
API and claim all account/address-book features work.

A further plan supplies administrator views and live Windows/Linux/macOS
compatibility tests against unchanged customer clients. No production rollout
or claim of complete auditing until those increments pass.

## Self-Review

This foundation covers the service portion of the approved spec, including
authentication, common directory, audit ingestion/reports, and deployment.
Client enforcement, lifecycle instrumentation, administrator UI, presence
probing, and installed-client compatibility explicitly remain subsequent work.
The five review-focus risks have tests in their owning tasks. No Git or live
server mutation is included.

## Execution Record (2026-10-14)

- [x] Database, migrations, request-local transactions, rollback, readiness.
- [x] Argon2id authentication, digest-only bearer tokens, account administration,
  expiration, throttling, revocation and last-administrator protection.
- [x] Common directory, admin-only mutations, atomic CSV import and safe export.
- [x] Identity-bound idempotent audit lifecycle, reports, interrupted telemetry
  and explicit gap handling.
- [x] Pinned runtime dependencies, isolated non-root Docker deployment, README,
  reproducible disposable-container HTTP smoke test.

Verification: management pytest 19 passed (one dependency deprecation warning);
existing Python tests 21 passed and 10 skipped; Apps Script Node tests 17 passed;
Docker build and Compose validation passed. Read-only, non-root Docker HTTP smoke
verified login, two employees, directory, session lifecycle and process-restart
persistence. Local `/readyz` returned ready. Production deployment and unchanged
installed-client compatibility were not exercised.

Independent review identified silent CSV export truncation, unpaginated employee
listing and contradictory completion outcomes. Each was reproduced by a failing
regression test and fixed. Reviewer confirmed all three fixes and independently
reran the then-17-test suite; two additional tests subsequently brought it to 19.

Ruling: grouped API tests in `tests/test_management.py` rather than splitting
fixtures and seven tiny test files; feature scope unchanged, tradeoff is a larger
single test module. Ruling: selected Python 3.14.2 for the container because that
version was available for local verification; Python 3.12 minimum remains declared
but was not separately tested. Existing request-limit/CSV/auth tests cover the
foundation, not a security certification or live client integration.

Residual verification gaps: no concurrent-reset stress test, full backup/restore
drill, production HTTPS/rate-limit validation, x86 Docker image build, or Rust/
Flutter compilation. No commits, pushes or live-service changes were made.
