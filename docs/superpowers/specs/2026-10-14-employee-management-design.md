# Employee Management With Existing Client Compatibility

Status: Proposed for review

## Objective

Give each employee an individual login, a common directory of all customers,
and reports for sessions launched through the managed employee application.
Keep the official OSS hbbs/hbbr services and unchanged customer RustDesk clients.
Do not replace or remove existing remote desktop, file transfer, clipboard,
audio, tunneling, or other connection features.

## Architecture

Add a separately deployable management API and database alongside hbbs/hbbr.
Neither service nor the RustDesk wire protocol is replaced. Use the client's
existing account and address-book integration where its request/response
contracts fit; do not claim full implementation of the upstream Pro API.

The employee build uses HTTPS for management traffic. Customer authentication
continues to use existing RustDesk passwords or attended approval. Customer
passwords are not imported into the management database or audit records.

Provide separate administrator and employee roles. Only administrators create,
disable, and reset employee accounts or edit the common directory. Every active
employee can view all directory entries; there are no customer assignments.
Use password hashing, revocable expiring sessions, login rate limits, and
administrator bootstrap from deployment secrets, not a compiled credential.

## Directory And Presence

Administrators add existing RustDesk IDs manually or import a validated CSV
export from Excel. Directory entries contain an internal ID, RustDesk ID,
customer name, device label, and optional notes. Validate lengths, duplicates,
and spreadsheet formula hazards on import/export.

Existing customer installations require no update if already configured for
the same hbbs/hbbr and server key. Devices on other servers require a separate
configuration change; the directory cannot silently migrate them.

Directory membership is not proof of online status. Reuse an existing RustDesk
online-query facility only after verifying its behavior against official OSS
hbbs. Until verified, show unknown presence rather than infer online status
from directory membership or old registration notifications.

## Session Audit

In managed employee mode, require an active employee login before initiating
outbound connections, including recent peers, direct IDs, URI/deep links,
file-transfer mode, and additional windows. Receiving ordinary customer
connections remains unchanged.

Create a server-generated audit session before initiation and record target ID,
employee ID derived from the authenticated session, connection mode, and
server timestamps. Update it on successful authentication, connection failure,
and closure. Repeated event submissions are idempotent. Heartbeats identify
abandoned sessions; missing termination produces an interrupted/unknown end,
not an invented clean disconnect or exact duration.

Reject new managed sessions if authorization/audit creation is unavailable.
Do not terminate an established remote session solely because management
telemetry is temporarily unavailable. Report telemetry gaps explicitly.

Reports show attempts, authenticated connections, outcomes, last activity,
and observed duration. They do not claim to record every action inside the
customer computer. File-transfer-only and other non-desktop modes must be
distinguishable in reports.

## Restrictions And Trust Boundary

Account disablement blocks subsequent managed-session authorization. Immediate
termination of existing sessions is not promised in the first increment.
Do not claim server-enforced client-side feature restrictions on unchanged
customer installations. Existing RustDesk permission controls remain usable.

An employee can bypass this application using an ordinary RustDesk client if
they possess customer credentials. Logs are employee-application-reported,
not complete server-attested logs. Signed binaries, client login, and API
tokens cannot eliminate that bypass. Mandatory fleet-wide enforcement would
be a separately approved server/client compatibility project.

## Delivery Slices

1. Management API: employee/admin authentication, revocation, directory CRUD,
   CSV import/export, audit lifecycle, migrations, Docker deployment, tests.
2. Employee client: reuse login/directory UI contracts, opt-in managed mode,
   lifecycle instrumentation and initiation-path coverage, no protocol changes.
3. Administrator views: employee management, shared directory, session report.
4. Compatibility verification against official OSS services and unchanged
   Windows/Linux/macOS customer clients before distributing installers.

Backend implementation language/database and production URL are to be chosen
in the implementation plan based on maintainability and the available build
environment; no live deployment is authorized by this document.

## Acceptance And Verification

- Two separate employees see the same directory and receive distinct audit
  identities; neither can manage accounts or edit protected directory records.
- Disabled/revoked credentials cannot start another managed session.
- All outbound initiation paths are reviewed and tested, not just the main
  Connect button.
- Success, denial, timeout, crash, duplicate events, management outage, and
  reconnect cases have explicit tested audit outcomes.
- An unchanged customer client can accept a managed employee connection with
  existing password/approval and retains existing protocol features.
- Presence remains unknown until a compatible live probe is verified.
- No passwords, access tokens, clipboard data, screen content, or transferred
  file contents are included in audit logs.
- Unit/API tests are not substitutes for installed-client compatibility tests.
- Existing unrelated changes, git history, remotes, and deployment remain
  untouched. No commit or push without a separate user request.
