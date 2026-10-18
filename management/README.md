# Sasthotech Employee Management API

Deployment walkthrough: [deploy/README.md](deploy/README.md). Automatic desktop
screen and employee-microphone capture is still incomplete; deploying media
endpoints does not enable capture.

Independent management API and console for employee accounts, a common customer
directory and employee-app-reported audits. Employee desktop integration is
implemented in source but still requires Rust/Flutter compilation and real-client
compatibility verification before distribution.
It does not discover devices, prove online status, enforce customer permissions,
or observe sessions made through an ordinary RustDesk installation. All existing
remote desktop features and hbbs/hbbr configuration remain unchanged.

## Local Test

From `management/`, using Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest tests -q
MANAGEMENT_DATABASE=/tmp/sasthotech-management.db .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 21114 --workers 1 --no-proxy-headers --no-access-log
```

Employee/admin console: `http://127.0.0.1:21114/console`.
API schema: `http://127.0.0.1:21114/docs`.
Set the same `MANAGEMENT_DATABASE` for bootstrap in another terminal:

```sh
MANAGEMENT_DATABASE=/tmp/sasthotech-management.db .venv/bin/python -m app.cli create-admin --username admin
```

The CLI prompts securely. `--password-file` also accepts a protected local file;
do not pass passwords as command-line arguments. There is no default account.
Run locally only on loopback; remote access requires HTTPS.

## Deployment

Run the separate `management/compose.yml` alongside, not instead of, the working
RustDesk Compose. This service does not modify or restart hbbs/hbbr.

```sh
docker compose -f management/compose.yml build
docker compose -f management/compose.yml up -d
docker compose -f management/compose.yml exec management python -m app.cli create-admin --username admin
```

Disposable-container verification (no production database or published port):

```sh
docker build -t sasthotech-management:local management
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true sasthotech-management:local python smoke.py
```

Configure `MANAGEMENT_PUBLIC_ORIGIN` in the deployment environment. It records
the intended HTTPS endpoint; it does not configure TLS, DNS, or a Host allowlist.
Expose only through a trusted local HTTPS reverse proxy. Example Nginx location
inside an existing TLS server block:

```nginx
location / {
    client_max_body_size 2m;
    proxy_pass http://127.0.0.1:21114;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
}
```

Proxy headers are deliberately not trusted. Login throttling therefore sees
the proxy address and shares its 50-attempt/15-minute budget; per-username
throttling is 10 attempts/15 minutes. Configure edge rate limiting for larger
teams; never enable arbitrary forwarded-header trust. Disable request-body and
authorization-header logging at the proxy. Authentication uses bearer tokens,
not cookies; no cross-origin browser access is enabled.

## API

- `/api/login`, `/api/currentUser`, `/api/logout`: basic RustDesk-compatible
  password-account envelope; no claim of complete upstream Pro API support.
- `/api/management/employees`: administrator account management; disable and
  password reset revoke all tokens. Employees cannot manage accounts.
- `/api/management/clients`: all employees read the same directory; only admins
  create, replace (`PUT`), delete, import, or export. Presence is `unknown`.
- `/api/management/clients/import`: raw UTF-8 CSV body, exact header
  `rustdesk_id,customer_name,device_label,notes`; 2 MiB/5000 rows maximum,
  all-or-nothing import. Export explicitly rejects directories over 5000 rows;
  use the paginated directory API for larger inventories. Export escapes formula-like cell prefixes; it does not
  preserve byte-identical values for spreadsheet-dangerous text.
- `/api/management/sessions`: authenticated creation with caller-generated UUID
  `request_id`, registered `client_id`, and mode. Identity comes from the token.
- `/api/management/sessions/{id}/events`: owner-only UUID `event_id`, `kind`
  (`authenticated`, `heartbeat`, `failed`, `closed`), optional bounded `outcome`.
- `/api/management/reports/sessions`: admins see all, employees only their own;
  pagination and UTC-offset-aware date filters. Audits identify their source as
  `employee_app_reported`, never server attestation.

Account disablement stops new API authorization; it does not terminate an
established remote connection. After 120 seconds without telemetry, active
records display as interrupted. A subsequent event permanently marks that gap;
reports do not claim exact duration across it. Client integration should send
heartbeats more often than this threshold. Event times use the API server clock.

## Persistence And Operations

The named `management-data` volume holds SQLite, WAL and shared-memory files.
Use one API worker, one replica, and local volume storage (not a network share).
Stop the API before copying the entire volume for backup; back up hbbs/hbbr's
separate identity/data directory independently. Restore to a separate test
volume, start the matching image, and verify accounts/directory/audits before
switching production. A restore drill has not been performed by this code.

Schema version 1 is migrated transactionally. A newer unknown schema fails
startup instead of silently downgrading. Snapshot before upgrades. Failed
database transactions roll back, lock waits are bounded, and database errors
return 503 without exposing SQL internals. Token values are stored only as
digests; passwords use Argon2id. Database files and backups remain sensitive.

Audit retention is indefinite in this increment: no automatic deletion or
public delete API. Establish company retention/backup requirements before a
production rollout, monitor volume growth, and keep reports access-controlled.
Existing installation-notification webhooks are not used as online presence.

## Employee Builds And Remaining Verification

Select employee mode and an HTTPS management origin in the focused desktop
workflow. Ordinary customer builds leave employee mode off. Company and employee
policy controls apply to managed builds only, and existing customer installations
do not need to change. The directory is independent of upstream Pro address-book
endpoints; those are not implemented or advertised.

Native compilation, installed Windows/Linux/macOS compatibility, deployment
HTTPS and a production restore rehearsal
remain verification/release gates. See `docs/employee-management-acceptance.md`.
Do not deploy or distribute an employee build as fully verified on the strength
of API/browser tests alone.
