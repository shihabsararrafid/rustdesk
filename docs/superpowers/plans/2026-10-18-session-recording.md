# Session Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically record remote-session video and the employee's selected local microphone, upload privately, and expose administrator playback without blocking sessions on media failures.

**Architecture:** Extend the independent management service with session-owned media and resumable uploads. Reuse RustDesk's video recorder and CPAL capture conventions, with a dedicated microphone sink and a bounded local spool. Server-side FFmpeg produces playback derivatives from timestamped original segments; employee/client attribution comes from authenticated audit sessions, not caller-supplied employee IDs.

**Tech Stack:** Existing Rust/Tokio/reqwest/CPAL, existing scrap video recorder, established WAV writer `hound`, Python/FastAPI/SQLite, FFmpeg/ffprobe, existing Flutter toolbar and browser console. Do not introduce a second audio engine, remote microphone source or new client/server protocol.

**Spec:** `docs/superpowers/specs/2026-10-18-session-recording-design.md`

## Global Constraints

- Start after accepted remote authentication; stop on last session reference.
- Record remote screen and selected employee microphone only, never remote audio or loopback.
- Continue remote sessions on media/storage/network failure; report each failure explicitly.
- Visible indicator, appropriate participant notice, explicit microphone selection and OS permission; respect remote recording permission.
- Administrator-only playback/download, authorization on every request including Range.
- Defaults: 30-day retention, 20 GiB server quota, 2 GiB employee spool cap, 2 GiB per asset, 1 MiB upload chunks.
- No secrets in manifests/logs, no public media routes or accepted filesystem paths.
- Preserve hbbs/hbbr, customer installations and existing connection features.
- No commit, push, production deployment or permission bypass.

## Review Focus

1. An upload interrupted between file write and metadata commit must resume without corruption (Tasks 1–2).
2. A revoked or different employee token cannot resume, finalize or download another session's media (Tasks 1–2).
3. Device defaults can be loopback sources; microphone selection must never silently fall back to output capture (Task 4).
4. Simultaneous sessions and display-window changes must not duplicate capture or stop another session's microphone (Tasks 3–4).
5. A codec change, microphone gap, crash or failed finalization must not produce apparently complete synchronized media (Tasks 3–6).

## Task 1: Recording Metadata And Independent Capture States

**Files:** create `management/app/recordings.py`, `management/app/migrations/003_recordings.sql`, `management/tests/test_recordings.py`; modify `management/app/database.py`, `settings.py`, `main.py`.

**Interfaces:** `POST /api/management/sessions/{session_id}/recordings` accepts `{request_id: UUID}` and idempotently returns `{id,screen_state,microphone_state,upload_state}` to the session owner. Only an authenticated remote-control session can start capture. `POST /api/management/recordings/{id}/events` accepts UUID event identity, stream kind (`screen`, `microphone`), state, bounded reason code and nonnegative monotonic offset. Server timestamps are authoritative for ingestion, offsets for synchronization.

- [ ] Add failing tests for wrong owner, disabled/revoked account, attempted-only session, non-desktop mode, duplicate creation/events, conflicting retries and independent video/audio failures. Start with:

```python
import pytest
from uuid import uuid4
from test_management import env

@pytest.fixture
def recording_env(env):
    api, login, _ = env
    headers = login()
    session = api.post('/api/management/sessions', headers=headers, json={
        'request_id': str(uuid4()), 'target_id': '123456789', 'mode': 'remote_control'})
    session_id = session.json()['id']
    api.post(f'/api/management/sessions/{session_id}/events', headers=headers,
        json={'event_id': str(uuid4()), 'kind': 'authenticated'})
    recording = api.post(f'/api/management/sessions/{session_id}/recordings',
        headers=headers, json={'request_id': str(uuid4())})
    assert recording.status_code == 201
    return api, headers, session_id, recording.json()['id']

def read_session_state(api, headers, session_id):
    rows = api.get('/api/management/reports/sessions', headers=headers).json()['items']
    return next(row['state'] for row in rows if row['id'] == session_id)

def test_microphone_denial_does_not_close_remote_session(recording_env):
    api, headers, session_id, recording_id = recording_env
    response = api.post(f'/api/management/recordings/{recording_id}/events', headers=headers,
        json={'event_id': str(uuid4()), 'stream': 'microphone', 'state': 'unavailable',
              'reason': 'permission_denied', 'offset_ms': 0})
    assert response.status_code == 200
    assert read_session_state(api, headers, session_id) == 'authenticated'
```

  These helpers use existing authenticated API fixtures and the owner-visible report, not direct database mutation.
- [ ] Run `PYTHONPATH=management python -m pytest management/tests/test_recordings.py -q` and observe failure before adding routes.
- [ ] Add version-3 transactional migration for recording groups, assets, upload chunks and media events. Preserve existing accounts, policies and audit history. Define UNIQUE owner/request and recording/event constraints; foreign keys prohibit orphan media. Reject unknown newer schema versions.
- [ ] Represent screen and microphone statuses separately. Allowed capture transitions: `starting -> active|unavailable|failed`; `active -> completed|failed`; crash recovery derives `interrupted` rather than completed. Unknown/missing media never implies success. Reasons: `permission_denied`, `no_device`, `peer_recording_denied`, `disk_full`, `device_disconnected`, `capture_error`, `upload_error`, `quota_exceeded`.
- [ ] Add validated storage settings and private media-root creation outside the static tree. Add migration and capture-state tests, then rerun the complete management suite.

## Task 2: Checksummed Resumable Storage And Authorized Downloads

**Files:** create `management/app/media_store.py`, `management/tests/test_media_upload.py`; extend `recordings.py`, deployment configuration and Docker volume definitions.

**Interfaces:** owner `POST /api/management/recordings/{id}/assets` creates a generated asset UUID from `{request_id,kind,display_index,segment_index,start_offset_ms,expected_bytes,sha256,format}`. Kinds are `screen`/`employee_microphone`; formats are `webm`, `mp4`, `wav`. `PUT /api/management/assets/{id}/chunks/{index}` takes raw bytes plus `X-Chunk-SHA256` and `X-Offset`. `GET /api/management/assets/{id}/upload-status` returns acknowledged offset. `POST /api/management/assets/{id}/finalize` verifies complete bytes/hash. All IDs are server-generated UUID paths, never client filenames.

- [ ] Write red tests for 1 MiB bounds, out-of-order offset, truncated request, duplicate/conflicting chunk, wrong final hash, concurrent quota reservation, path traversal, revoked token and another employee's UUID. Include fault injection immediately after durable file write and immediately before metadata commit.
- [ ] Run `PYTHONPATH=management python -m pytest management/tests/test_media_upload.py -q` before implementation.
- [ ] Persist each chunk under a generated identity using exclusive temporary-file creation, flush/fsync and atomic promotion. Reconcile unacknowledged bytes against chunk metadata after interruption. Reserve full expected-byte quota transactionally before accepting assets; count pending uploads and derivative reservations, not only completed files.
- [ ] Validate final byte count and full checksum before switching upload state to uploaded. Finalization is idempotent; incomplete input remains pending or failed. File/DB crash reconciliation must never label a missing file uploaded.
- [ ] Add administrator-only listing and streaming routes `GET /api/management/recordings`, `GET /api/management/assets/{id}/content`; support one validated byte range and return 416 for invalid/multiple ranges. Authorize before file lookup/streaming and use no-store headers; employees receive upload metadata, not playback access.
- [ ] Run upload/authorization tests and a restart/resume integration test; verify no media can be fetched from `/console/assets`.

## Task 3: Native Session Recorder And Durable Upload Spool

**Files:** create `src/employee_recording.rs`, `src/employee_recording/{manifest,upload}.rs`; modify `src/employee_management.rs`, `src/client.rs`, `src/client/io_loop.rs`, `libs/scrap/src/common/record.rs`, and module declarations.

**Interfaces:** `RecordingSession::start(audit_id, selected_microphone) -> Result<RecordingSession>` starts only after audit authentication acknowledgement. The guard owns a monotonic epoch, bounded event channel, stream status and local manifest. Recorder notifications carry recording UUID, display/segment identity and actual file state. `RecordingSession::finish()` finalizes media asynchronously; failures emit media events and never return a remote-connection error.

- [ ] Add native mock-HTTP tests for idempotent create/upload/finalize, 401, response timeout, retry of the exact chunk, local restart and spool cap. Inject a filesystem/capture adapter to test disk-full without exhausting the workstation.
- [ ] Preserve the ordinary recorder API with optional context fields defaulting off. Extend recorder notifications to report open/write/finalization errors, segment file paths, codec and display boundaries; do not rely on the existing `record_screen` method swallowing recorder creation errors.
- [ ] Force managed auto-record after authenticated default-session start only if peer recording permission permits it. Retain normal recording behavior in customer builds. Use actual video-track creation and frame/write callbacks for active status, not just a UI toggle.
- [ ] Persist minimal per-user manifests and incomplete assets with private permissions. Do not store bearer tokens. Resume only after fresh login identifies the same owner; quarantine or explicitly fail another owner's pending upload.
- [ ] Upload finalized segments through Task 2, with bounded concurrency and retries; keep local originals until verified server finalization. At the 2 GiB spool cap stop capture for that stream and report disk/quota failure, without deleting unuploaded evidence or disconnecting the remote session.
- [ ] Test reconnect creates a new audit/recording group, extra display windows do not create duplicate microphone owners, and runtime teardown flushes metadata without indefinite waits. Unfinished files after crash remain interrupted until validated recovery.
- [ ] Run `cargo test --lib employee_recording` and desktop compile checks where available. Record unavailable native checks explicitly; syntax/source tests are not equivalents.

## Task 4: Selected Local Microphone And Common Clock

**Files:** create `src/employee_recording/microphone.rs`; modify `Cargo.toml`/`Cargo.lock` for `hound`, platform microphone permission integration and Flutter device selection.

**Interfaces:** `MicrophoneCapture::attach(device_id, session_epoch) -> Result<MicrophoneSubscription>` uses CPAL input only and writes WAV segments through `hound`. Each subscription records clock offsets and exact missing intervals; it cannot send a remote protocol message. A shared capture manager reference-counts subscriptions for simultaneous sessions.

- [ ] Write tests with deterministic fake samples and clocks: nonzero start offset, unplug/reconnect gap, two simultaneous sessions, stop-one/continue-other, permission denied, no device and full producer queue. Compare resulting WAV headers/sample counts with the established reader.
- [ ] Enumerate input devices and require employee selection/authorization. Do not infer physical microphones purely from device names, select default loopback, or silently change sources when the selected device disappears. Reopening the same selected source after a gap records a new segment.
- [ ] Use bounded nonblocking CPAL callbacks; move file I/O/encoding to a worker. Overrun produces a timestamped missing interval rather than invented continuity. Capture must remain separate from audio-service/voice-call subscriptions and remote audio decoding.
- [ ] Integrate Windows/macOS/Linux microphone permission/device handling. If the OS denies capture, emit microphone unavailable while video and remote control continue. Stop hardware capture after the final subscription leaves; finalize WAV headers before upload.
- [ ] Add synthetic waveform fixtures and verify no remote playback or loopback bus enters recordings. Run permission/device-unplug tests on each real OS; missing hardware/platform access stays an unverified release gate.

## Task 5: Employee Recording Indicator And Explicit Failure UX

**Files:** create `flutter/lib/models/session_recording_model.dart` and `flutter/test/session_recording_model_test.dart`; modify `src/flutter_ffi.rs`, `src/flutter.rs`, `flutter/lib/desktop/widgets/remote_toolbar.dart`, and `flutter/lib/common/widgets/toolbar.dart` only where its shared recording control is called by the desktop toolbar.

- [ ] Add failing widget tests for starting, screen active, microphone denied, capture stopped, upload pending/failed and no-media states. Use the existing desktop toolbar, not a replacement session surface.
- [ ] Publish typed session-scoped media events with no filenames/secrets to Flutter. Show separate screen, microphone and upload indicators, with tooltips and accessible names. Never show recording active merely because automatic recording was requested.
- [ ] Provide microphone selection and OS-permission actions, and persist selection without credentials. Explain when the selected microphone is attached to multiple sessions. Explicit user/OS interruption emits an event and visible state; no hidden capture or silent stop.
- [ ] Keep the connection usable on every capture/upload error. Respect peer recording denial and surface its reason. Test reconnect and moved-display windows without duplicate indicators or capture subscriptions.
- [ ] Run Flutter analysis/widget tests and native-screen smoke checks; record any unavailable toolchain rather than claiming a passing desktop UI.

## Task 6: Bounded Playback Processing And Administrator Review

**Files:** create `management/app/media_processing.py`, `management/tests/test_media_processing.py`; extend console assets, recording routes, Dockerfile and smoke tests.

**Interfaces:** CLI `python -m app.cli process-recordings --once` atomically leases one ready manifest and creates a generated MP4 derivative. Inputs must be completed verified assets. A lease expires to interrupted/retryable after a crash; ready requires a verified derivative and durable metadata commit.

- [ ] Create synthetic video and employee-microphone fixtures with an offset/gap. Assert derivative duration and audio placement, employee-only audio mapping, preserved originals, failed-probe behavior, timeout and concurrent-worker lease exclusion.
- [ ] Install FFmpeg/ffprobe in the service image; call argument arrays without a shell. Explicitly allow only local protocols/formats, prohibit network inputs and cap dimensions/duration/memory/runtime. Validate segment metadata against probed media rather than trusting client declarations.
- [ ] Process one job at a time. Account for derivatives in reserved quota, store under generated paths and promote atomically. Preserve source tracks on processing failure; expose the error, not a fake playback URL.
- [ ] Add administrator recording views linked to session reports, separate capture/upload/processing states, Range-authenticated playback, original downloads and deletion confirmation. Employee role must not see or fetch playback. Fetch authorized media using the existing memory-held token, not tokens in URLs; do not buffer an entire multi-GiB recording into a browser Blob.
- [ ] For browser playback, implement a dedicated short-lived, HttpOnly, Secure, SameSite=Strict media-session cookie created from administrator bearer authentication, scoped only to media routes. Validate role/revocation on each media request; protect cookie issuance/deletion against cross-origin requests. Local HTTP preview is explicitly development-only and cannot issue a production Secure playback session.
- [ ] Browser-test partial/video-only/audio-only/failed media, revoked admin access, seeks, expired playback authorization, and malicious metadata. Capture desktop/mobile screenshots and verify no layout overlap.

## Task 7: Retention, Deployment And End-To-End Acceptance

**Files:** extend `management/app/cli.py`, `settings.py`, Compose, recovery tools, README, `management/tests/test_media_retention.py`, desktop CI and `docs/employee-management-acceptance.md`.

- [ ] Write failing tests for 30-day cutoff, dry-run versus apply, active/pending upload exclusion, filesystem deletion failure, retained session history and expiring playback credentials.
- [ ] Implement `cleanup-recordings --dry-run` and `cleanup-recordings --apply`; persist deletion/expiry events and retryable failures. Delete media, not audit sessions. Explain backup-retention obligations and encryption-at-rest requirements.
- [ ] Persist media and manifests in separate private volumes. Extend backup/restore to include a consistent database/media manifest snapshot and verify checksums after restoring to a new disposable location. Do not overwrite production volumes.
- [ ] Extend Docker smoke with authenticated media upload, corrupt chunk rejection, finalize, processing, admin Range playback, retention dry run and service restart. Run all existing backend/browser/registration suites plus native checks where available.
- [ ] Run real Windows/macOS/Linux screen-plus-microphone capture: accepted session, speech/screen alignment, peer recording denied, microphone denied/unplugged, two concurrent sessions, display/codec change, crash and failed upload. Verify no remote audio is present and ordinary customer clients still connect unchanged.
- [ ] Finish with exact implemented/verified/unverified status. Do not deploy, push or distribute as verified if native capture or storage recovery checks remain unavailable.

## Self-Review And Execution Handoff

Tasks 1–2 own authenticated private storage; Tasks 3–5 own actual native capture
and visible failure reporting; Task 6 owns playback; Task 7 owns retention and
release proof. All five review-focus risks have explicit tests in the owning
task. The previously approved native execution method is retained. Product code
has not changed for recording, and there is no claim that recording is enabled.

The desktop/shared toolbar paths were checked against this checkout before
saving the plan. Unrelated existing employee-management changes stay untouched.
