import json
import re
import secrets
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool

from .auth import require_admin, require_user
from .database import connect_database, recheck_authorization
from .employees import database
from .security import digest
from . import media_store

router = APIRouter(prefix='/api/management')


class CreateRecording(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


class CaptureEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID
    stream: Literal['screen', 'microphone']
    state: Literal['starting', 'active', 'completed', 'unavailable', 'failed']
    reason: Literal['permission_denied', 'no_device', 'peer_recording_denied', 'disk_full',
                    'device_disconnected', 'capture_error', 'upload_error', 'quota_exceeded'] | None = None
    offset_ms: int = Field(ge=0, le=7 * 86400000)


class CreateAsset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    kind: Literal['screen', 'employee_microphone']
    display_index: int = Field(ge=0, le=255)
    segment_index: int = Field(ge=0, le=100000)
    start_offset_ms: int = Field(ge=0, le=7 * 86400000)
    expected_bytes: int = Field(gt=0, le=2 * 1024**3)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    format: Literal['webm', 'mp4', 'wav']

    @model_validator(mode='after')
    def valid_format(self):
        if (self.kind == 'employee_microphone') != (self.format == 'wav'):
            raise ValueError('Microphone requires WAV; screen requires WebM or MP4')
        return self


def owner_recording(db, rid, user):
    row = db.execute('SELECT * FROM recordings WHERE id=? AND employee_id=? AND deleted_at IS NULL', (str(rid), user['id'])).fetchone()
    if row is None:
        raise HTTPException(404, 'Recording not found')
    return row


def owner_asset(db, aid, user):
    row = db.execute('SELECT a.* FROM media_assets a JOIN recordings r ON a.recording_id=r.id '
                     'WHERE a.id=? AND r.employee_id=? AND r.deleted_at IS NULL', (str(aid), user['id'])).fetchone()
    if row is None:
        raise HTTPException(404, 'Asset not found')
    return row


@router.post('/sessions/{sid}/recordings', status_code=201)
def create(sid: UUID, body: CreateRecording, user=Depends(require_user), db=Depends(database)):
    session = db.execute('SELECT * FROM audit_sessions WHERE id=? AND employee_id=?', (str(sid), user['id'])).fetchone()
    if not session or session['mode'] != 'remote_control' or session['authenticated_at'] is None:
        raise HTTPException(409, 'Recording requires an authenticated remote-control session')
    existing = db.execute('SELECT * FROM recordings WHERE session_id=? AND request_id=?', (str(sid), str(body.request_id))).fetchone()
    if existing:
        return dict(existing)
    if session['state'] != 'authenticated':
        raise HTTPException(409, 'Session is no longer active')
    uid, now = str(uuid4()), time.time()
    db.execute('INSERT INTO recordings (id,request_id,session_id,employee_id,created_at,updated_at) VALUES (?,?,?,?,?,?)',
               (uid, str(body.request_id), str(sid), user['id'], now, now))
    return dict(db.execute('SELECT * FROM recordings WHERE id=?', (uid,)).fetchone())


@router.post('/recordings/{rid}/events')
def event(rid: UUID, body: CaptureEvent, user=Depends(require_user), db=Depends(database)):
    recording = owner_recording(db, rid, user)
    existing = db.execute('SELECT * FROM media_events WHERE recording_id=? AND event_id=?', (str(rid), str(body.event_id))).fetchone()
    if existing:
        if any(existing[key] != getattr(body, key) for key in ('stream', 'state', 'reason', 'offset_ms')):
            raise HTTPException(409, 'Conflicting capture event retry')
        return {'ok': True}
    column = body.stream + '_state'
    previous = recording[column]
    if previous in ('completed', 'unavailable', 'failed'):
        raise HTTPException(409, 'Capture stream is terminal')
    if body.state == 'completed' and previous != 'active':
        raise HTTPException(409, 'Capture never became active')
    db.execute('INSERT INTO media_events VALUES (?,?,?,?,?,?,?)',
               (str(rid), str(body.event_id), body.stream, body.state, body.reason, body.offset_ms, time.time()))
    db.execute(f'UPDATE recordings SET {column}=?,{body.stream}_reason=?,updated_at=? WHERE id=?',
               (body.state, body.reason, time.time(), str(rid)))
    return {'ok': True}


@router.post('/recordings/{rid}/assets', status_code=201)
def create_asset(rid: UUID, body: CreateAsset, request: Request, user=Depends(require_user), db=Depends(database)):
    owner_recording(db, rid, user)
    existing = db.execute('SELECT * FROM media_assets WHERE recording_id=? AND request_id=?', (str(rid), str(body.request_id))).fetchone()
    if existing:
        if any(existing[key] != value for key, value in body.model_dump(exclude={'request_id'}).items()):
            raise HTTPException(409, 'Conflicting asset retry')
        return dict(existing)
    settings = request.app.state.settings
    reserved = db.execute("SELECT coalesce(sum(expected_bytes),0) FROM media_assets WHERE state NOT IN ('expired','deleted')").fetchone()[0]
    # Finalization temporarily keeps both chunks and original; reserve both.
    if body.expected_bytes > settings.media_asset_bytes or 2 * (reserved + body.expected_bytes) > settings.media_quota_bytes:
        raise HTTPException(507, 'Media quota exceeded')
    uid, now = str(uuid4()), time.time()
    db.execute('INSERT INTO media_assets (id,request_id,recording_id,kind,display_index,segment_index,start_offset_ms,expected_bytes,sha256,format,created_at,updated_at) '
               'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
               (uid, str(body.request_id), str(rid), body.kind, body.display_index, body.segment_index,
                body.start_offset_ms, body.expected_bytes, body.sha256, body.format, now, now))
    return dict(db.execute('SELECT * FROM media_assets WHERE id=?', (uid,)).fetchone())


@router.put('/assets/{aid}/chunks/{index}')
async def upload(aid: UUID, index: int, request: Request,
                 x_chunk_sha256: str = Header(pattern=r'^[0-9a-f]{64}$'), x_offset: int = Header(ge=0),
                 user=Depends(require_user)):
    if index < 0 or index > 100000:
        raise HTTPException(422, 'Invalid chunk index')
    data = await request.body()
    def save():
        with connect_database(request.app.state.settings.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            recheck_authorization(db, request)
            row = owner_asset(db, aid, user)
            try:
                return media_store.write_chunk(db, request.app.state.settings, row, index, x_offset, x_chunk_sha256, data)
            except OSError as exc:
                raise HTTPException(507, 'Media storage unavailable') from exc
    return await run_in_threadpool(save)


@router.get('/assets/{aid}/upload-status')
def status(aid: UUID, user=Depends(require_user), db=Depends(database)):
    row = owner_asset(db, aid, user)
    return {'offset': row['received_bytes'], 'state': row['state']}


@router.post('/assets/{aid}/finalize')
def finalize(aid: UUID, request: Request, user=Depends(require_user), db=Depends(database)):
    row = owner_asset(db, aid, user)
    try:
        return media_store.finalize(db, request.app.state.settings, row)
    except OSError as exc:
        raise HTTPException(507, 'Media storage unavailable') from exc


@router.get('/recordings', dependencies=[Depends(require_admin)])
def listing(limit: int = 25, offset: int = 0, session_id: UUID | None = None, db=Depends(database)):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, 'Invalid pagination')
    where, params = (' WHERE r.session_id=?', [str(session_id)]) if session_id else ('', [])
    rows = db.execute('SELECT r.*,u.username AS employee_name,s.target_id FROM recordings r '
                      'JOIN users u ON r.employee_id=u.id JOIN audit_sessions s ON s.id=r.session_id' + where +
                      ' ORDER BY r.created_at DESC,r.id LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item['assets'] = [dict(a) for a in db.execute('SELECT id,kind,display_index,segment_index,start_offset_ms,expected_bytes,format,state FROM media_assets WHERE recording_id=?', (row['id'],))]
        if row['updated_at'] < time.time() - 120:
            for column in ('screen_state', 'microphone_state'):
                if item[column] in ('starting', 'active'):
                    item[column] = 'interrupted'
        items.append(item)
    return {'items': items, 'total': db.execute('SELECT count(*) FROM recordings r' + where, params).fetchone()[0]}


def playback_admin(request: Request):
    if request.headers.get('authorization'):
        return require_admin(require_user(request))
    cookie = request.cookies.get('__Secure-management-media', '')
    with connect_database(request.app.state.settings.database_path) as db:
        row = db.execute('SELECT u.* FROM media_sessions m JOIN auth_sessions a ON m.auth_token_hash=a.token_hash '
                         'JOIN users u ON a.user_id=u.id WHERE m.token_hash=? AND m.expires_at>? '
                         'AND a.expires_at>? AND a.revoked_at IS NULL AND u.disabled=0 AND u.role=\'admin\'',
                         (digest(cookie), time.time(), time.time())).fetchone()
    if not row:
        raise HTTPException(401, 'Administrator playback authorization required')
    return dict(row)


@router.post('/media-session', dependencies=[Depends(require_admin)])
def playback_session(request: Request, response: Response, db=Depends(database)):
    origin = request.headers.get('origin')
    # TLS may terminate at the trusted reverse proxy. A bearer-authorized,
    # exact HTTPS Origin plus a Secure cookie avoids trusting forwarded headers.
    if origin != request.app.state.settings.public_origin:
        raise HTTPException(403, 'Playback session requires same-origin HTTPS')
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM media_sessions WHERE expires_at<?', (time.time(),))
    db.execute('INSERT INTO media_sessions VALUES (?,?,?)',
               (digest(token), digest(request.headers['authorization'][7:]), time.time() + 300))
    response.set_cookie('__Secure-management-media', token, max_age=300, httponly=True, secure=True,
                        samesite='strict', path='/api/management/assets')
    return {'expires_in': 300}


@router.get('/assets/{aid}/content')
def content(aid: UUID, request: Request, user=Depends(playback_admin)):
    with connect_database(request.app.state.settings.database_path) as db:
        row = db.execute('SELECT a.* FROM media_assets a JOIN recordings r ON a.recording_id=r.id '
                         "WHERE a.id=? AND a.state='uploaded' AND r.deleted_at IS NULL", (str(aid),)).fetchone()
        if not row:
            raise HTTPException(404, 'Media unavailable')
        path = media_store.asset_dir(request.app.state.settings, aid) / ('original.' + row['format'])
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Media missing')
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        value = request.headers.get('range')
        if value:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
            if not match or not any(match.groups()):
                raise HTTPException(416, 'Invalid range', headers={'Content-Range': f'bytes */{size}'})
            a, b = match.groups()
            if a:
                start, end = int(a), min(int(b), size - 1) if b else size - 1
            else:
                if int(b) == 0:
                    raise HTTPException(416, 'Invalid range')
                start = max(0, size - int(b))
            if start > end or start >= size:
                raise HTTPException(416, 'Unsatisfiable range', headers={'Content-Range': f'bytes */{size}'})
            code = 206
        handle = path.open('rb')
    def stream():
        try:
            handle.seek(start)
            remaining = end - start + 1
            while remaining:
                block = handle.read(min(65536, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
        finally:
            handle.close()
    headers = {'Content-Length': str(end - start + 1), 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store',
               'Content-Disposition': f'inline; filename="{aid}.{row["format"]}"'}
    if code == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    return StreamingResponse(stream(), status_code=code,
        media_type={'webm': 'video/webm', 'mp4': 'video/mp4', 'wav': 'audio/wav'}[row['format']], headers=headers)
