# Session Screen And Employee Microphone Recording

Status: Proposed for review

## Confirmed Scope

Automatically record the remote session's screen and the employee computer's
selected microphone, beginning after successful remote authentication. Do not
capture remote computer audio, remote microphone, employee desktop outside the
session, or a system-loopback audio device. Sessions must continue when screen
recording, microphone permission/capture, storage or upload fails. Each failure
must have an explicit independent audit status; missing media is never success.

Recording is visible to the employee and disclosed through the organization's
appropriate participant notices. Respect operating-system microphone permission
and the remote peer's existing recording permissions; do not bypass denial.
No capture before authentication or after the last associated session closes.

## Source Findings

- `libs/scrap/src/common/record.rs`: `RecorderApi` exposes `write_video`; its
  WebM implementation adds a video track but no microphone/audio track.
- `src/client/io_loop.rs`: existing automatic outgoing recording begins when
  the first video thread appears and respects `record_permission`.
- `src/client.rs`: recorder contexts identify display and camera; recordings
  can split when codec, dimensions or display changes.
- `src/hbbs_http/record_upload.rs`: existing uploader posts to `/api/record`
  and addresses files by name. It does not supply our authenticated
  employee/session-scoped upload contract. It cannot safely be enabled as-is.
- `src/server/audio_service.rs`: existing CPAL capture includes device selection
  and system-audio paths. Reuse supported device/capture conventions, but do not
  start the system-audio/voice-call service as a substitute for local recording.

## Chosen Architecture

Keep hbbs/hbbr and customer installations unchanged. The employee build records
locally and uploads to the management service over its authenticated HTTPS API.
Store private media separately from the SQLite database. Link every asset to
the audit session, employee, remote target, display and recording segment.

Reuse RustDesk's video recorder and native capture libraries. Add a dedicated
employee microphone sink, using an established WAV writer rather than a custom
audio container implementation. It must not broadcast the microphone into the
remote session or silently select a loopback/monitor source. Employee selects
and authorizes the microphone; no usable input means microphone-unavailable.

Video and microphone run independently: video-only and audio-only outcomes are
allowed and accurately labelled. Only default remote-control sessions trigger
screen/microphone recording; camera, file-transfer-only, terminal and tunnel
connections report recording not applicable rather than inventing a screen.

## Synchronization And Playback

Persist recording IDs, stream segment start offsets and capture timestamps on
one monotonic session clock. Codec/resolution/display changes create identified
video segments; microphone gaps/disconnects retain their true offsets instead
of compressing time or labeling silence as captured audio.

Use bounded server-side FFmpeg processing to create browser-compatible MP4
playback derivatives with the employee microphone as the only audio source.
Preserve original tracks and their manifest for administrator download. A
processing failure must not delete usable originals. No global sound capture
or remote audio stream may enter the mix.

Use generated internal filenames, argument arrays, offline-only protocols,
explicit input formats, resource/time limits and one processing job at a time.
Probe and validate uploaded media before processing; never invoke a shell with
user filenames or allow media to fetch external resources. FFmpeg introduces
server CPU/storage requirements and is not needed inside customer installations.

## Recording Lifecycle And Failures

Create separate recording records associated with the authenticated audit
session. Screen and microphone states include starting, active, completed,
unavailable and failed, with bounded reason codes such as permission_denied,
no_device, peer_recording_denied, disk_full, device_disconnected and capture_error.
Upload states include pending, uploading, uploaded, failed and expired.
Processing states include pending, processing, ready and failed.

Mark active only after actual media capture begins. Mark uploaded only after
the backend durably verifies the expected bytes and checksum. Surface microphone
permission denial separately from missing/failed screen capture. If the
management service itself is unavailable, retain bounded local diagnostic
events for later submission; server reports unknown/interrupted until received.

Show a recording indicator in the employee session toolbar with separate
microphone and upload state. Display actionable permission/device errors without
blocking remote control. Do not permit stopping an automatic managed recording
silently: user/OS interruptions produce explicit stopped/unavailable events.

On disconnect/reconnect, finalize each attempt separately and restart recording
only after the new attempt authenticates. Crash recovery never labels an
unfinished file or missing finalization event complete. Shared display windows
must not duplicate microphone capture for one underlying session. Concurrent
remote sessions may attach to one shared selected-microphone capture pipeline,
with per-session timestamps and lifetime references; warn employees that their
microphone accompanies each active recorded session.

## Upload Contract And Storage

Use session-owner authenticated endpoints for creating manifests, reporting
capture status, uploading numbered chunks and finalizing assets. Generate UUID
recording/asset IDs server-side. Never accept filesystem paths from clients or
trust an employee ID supplied in the body. Administrators can review assets but
cannot submit events as another employee.

Chunks are at most 1 MiB, fitting the existing 2 MiB management request bound.
Require sequential offsets, content length, SHA256 checksums and an idempotent
chunk identity. Retrying an acknowledged chunk does not duplicate data; conflicting
retries fail explicitly. Restart-resumable manifests track acknowledged offsets.
Finalization validates total bytes/checksum before atomically promoting media.

Employees can submit and inspect upload status for their own sessions only.
Administrator-only listing, playback, download and deletion use authorization on
every request, including HTTP Range. No public media URLs, directory listings,
raw-path download parameters or media served from the console static directory.
Capture credentials are never part of media metadata or manifests.

Proposed configurable defaults: 30-day retention, 20 GiB server media quota,
2 GiB employee local spool cap, and a 2 GiB per-asset cap. Quota failures preserve
remote access and create explicit upload/storage failures. Never overwrite or
silently evict unuploaded recordings when the local spool is full. Local spool
files use per-user permissions; automatic deletion follows verified upload and
retention rules. Media/backup encryption-at-rest is a deployment requirement,
not something implied by HTTPS or Unix permissions.

Retention uses an explicit scheduled cleanup command with a dry run. Persist a
deleted/expired metadata status and deletion audit; do not erase the underlying
session history. Document that deletion from backups follows backup retention.

## Verification And Release Gates

- API authorization: employee ownership, revoked tokens, administrator-only
  playback, chunk bounds, checksums, duplicate/conflicting retries, interrupted
  finalization, storage exhaustion and path traversal.
- Independent media failures: mic permission denial/no device/unplug, remote
  recording denial, no video frames, disk full, offline API and exhausted retry.
- Permission and capture tests confirm remote audio is never included and the
  microphone is never sent to the remote computer by the recording pipeline.
- Synthetic audio/video fixtures verify timestamp offsets, gaps, codec/display
  splits, playback derivatives, processing failure and retention deletion.
- Crash/restart/resume tests verify unknown states are not labeled complete.
- Two simultaneous sessions verify shared-microphone ownership and correct stop.
- Real Windows/macOS/Linux tests verify device choice, OS permissions, visible
  indicators, recorded speech, screen/audio synchronization and readable files.
- Existing RustDesk features and unchanged customer clients require regression
  checks. API unit tests do not establish native capture success.

## Boundaries

This spec adds work; no recording implementation or upload storage is enabled
by writing it. Existing Rust/Flutter compilation and installed-client acceptance
gates remain. No live deployment, permission bypass, silent recording, commit
or push is authorized. After written-spec review, create the task-by-task
implementation plan using the established native execution method.
