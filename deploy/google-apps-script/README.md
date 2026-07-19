# Client Registration Webhook Deployment

This guide deploys the Google Apps Script webhook that receives desktop client
registration POSTs, appends one deduplicated row to a Google Sheet, and emails
`shihabsararrafid@gmail.com`.

The web app runs **as you** (the Sheet owner) and is reachable by **Anyone**
with the deployment URL. That public reachability is intentional; every request
must still include a shared secret token in the JSON body (`token` field). The
client binary validates nothing at the HTTP layer beyond HTTPS—token mismatch is
rejected inside `doPost` before any row or email is created.

**Never commit** the Sheet ID, recipient address, client token, or deployment
URL to source control. Store them only in Apps Script properties and GitHub
repository secrets.

## Prerequisites

- A Google account that owns the registration Sheet (use
  `shihabsararrafid@gmail.com`).
- Repository admin access to add GitHub Actions secrets.
- Local copies of `RegistrationCore.gs` and `Code.gs` from this directory.

## 1. Create the Google Sheet

1. Sign in as `shihabsararrafid@gmail.com`.
2. Create a new Google Sheet (any name).
3. Copy the **Sheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`

The script creates a `Registrations` tab automatically on first POST if it does
not exist.

## 2. Create the Apps Script project

1. In the Sheet, open **Extensions → Apps Script**.
2. Remove any default `Code.gs` stub content.
3. Add two script files with the exact names from this repo:
   - `RegistrationCore.gs` — paste contents from
     `deploy/google-apps-script/RegistrationCore.gs`
   - `Code.gs` — paste contents from `deploy/google-apps-script/Code.gs`
4. Save the project.

## 3. Set script properties

Open **Project Settings** (gear icon) → **Script properties** → **Add script
property**. Add these three properties (names must match exactly):

| Property | Value |
|----------|-------|
| `SHEET_ID` | The ID copied from the Sheet URL (step 1) |
| `RECIPIENT_EMAIL` | `shihabsararrafid@gmail.com` |
| `CLIENT_TOKEN` | A random secret of at least 32 bytes (see below) |

Generate a token locally (do not reuse example values):

```bash
openssl rand -base64 32
```

Paste the output as `CLIENT_TOKEN`. You will reuse the same value as the GitHub
secret `SASTHOTECH_REGISTRATION_TOKEN` in step 6.

## 4. Deploy as web app

1. Click **Deploy → New deployment**.
2. Select type **Web app**.
3. Configure:
   - **Description:** e.g. `Client registration webhook`
   - **Execute as:** **Me** (`shihabsararrafid@gmail.com`)
   - **Who has access:** **Anyone**
4. Click **Deploy** and authorize the requested scopes (Spreadsheets, send email
   as you).
5. Copy the **Web app URL**. It must end with `/exec` (not `/dev`).

## 5. Add a retry trigger

Failed emails are marked `email_failed` on the sheet. The `retryFailedEmails`
function retries only those rows.

1. In the Apps Script editor, open **Triggers** (clock icon).
2. **Add Trigger**:
   - Function: `retryFailedEmails`
   - Event source: **Time-driven**
   - Type: **Minutes timer**
   - Interval: **Every 15 minutes**
3. Save.

## 6. Configure GitHub repository secrets

In the RustDesk fork repository on GitHub:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `SASTHOTECH_REGISTRATION_URL` | The `/exec` web app URL from step 4 |
| `SASTHOTECH_REGISTRATION_TOKEN` | The same value as `CLIENT_TOKEN` from step 3 |

Do not log or echo these values in CI. The **Sasthotech Desktop Build**
workflow (`sasthotech-desktop` profile) validates that both secrets are set and
that the URL uses `https://` before compiling desktop installers. Full upstream
profile builds omit this check and compile with registration disabled when
secrets are absent.

## 7. Smoke test (optional)

After deployment, POST a valid JSON body to the `/exec` URL (replace placeholders):

```bash
curl -sS -X POST "$SASTHOTECH_REGISTRATION_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "<CLIENT_TOKEN>",
    "installation_id": "3d9d36e2-70c1-4c1d-a63d-cf45f314e922",
    "rustdesk_id": "123456789",
    "hostname": "smoke-test",
    "os": "linux",
    "app_version": "1.4.9",
    "registered_at": "2026-07-19T12:00:00Z"
  }'
```

Expected response: `{"accepted":true,"duplicate":false}`. Confirm one row in
the `Registrations` sheet and one notification email to
`shihabsararrafid@gmail.com`.

## Security notes

- The deployment URL is public; only callers knowing `CLIENT_TOKEN` can create
  rows. Rotate the token in both Script properties and GitHub secrets together.
- `token` is never written to the Sheet—only registration metadata columns are
  stored.
- Keep Sheet ID, recipient, token, and deployment URL out of git, issue
  comments, and build logs.
