import hashlib
from uuid import uuid4

import pytest

from test_management import env, employee


@pytest.fixture
def media(env):
    api, login, settings = env
    admin = login()
    employee(api, admin)
    owner = login('employee', 'employee-test-password')
    sid = api.post('/api/management/sessions', headers=owner, json={
        'request_id': str(uuid4()), 'target_id': '123', 'mode': 'remote_control'}).json()['id']
    assert api.post(f'/api/management/sessions/{sid}/events', headers=owner,
                    json={'event_id': str(uuid4()), 'kind': 'authenticated'}).status_code == 200
    response = api.post(f'/api/management/sessions/{sid}/recordings', headers=owner,
                        json={'request_id': str(uuid4())})
    assert response.status_code == 201, response.text
    return api, admin, owner, sid, response.json()['id'], settings


def asset(api, owner, rid, content=b'media', kind='screen', format='webm'):
    response = api.post(f'/api/management/recordings/{rid}/assets', headers=owner, json={
        'request_id': str(uuid4()), 'kind': kind, 'display_index': 0,
        'segment_index': 0, 'start_offset_ms': 0, 'expected_bytes': len(content),
        'sha256': hashlib.sha256(content).hexdigest(), 'format': format})
    assert response.status_code == 201, response.text
    return response.json()['id']


def chunk(api, owner, aid, content=b'media', index=0, offset=0):
    headers = dict(owner, **{'X-Chunk-SHA256': hashlib.sha256(content).hexdigest(), 'X-Offset': str(offset)})
    return api.put(f'/api/management/assets/{aid}/chunks/{index}', headers=headers, content=content)


def test_capture_failure_is_independent_and_session_continues(media):
    api, admin, owner, sid, rid, _ = media
    response = api.post(f'/api/management/recordings/{rid}/events', headers=owner, json={
        'event_id': str(uuid4()), 'stream': 'microphone', 'state': 'unavailable',
        'reason': 'permission_denied', 'offset_ms': 0})
    assert response.status_code == 200
    row = api.get('/api/management/recordings', headers=admin).json()['items'][0]
    assert row['microphone_state'] == 'unavailable'
    assert row['screen_state'] == 'starting'
    assert api.get('/api/management/reports/sessions', headers=owner).json()['items'][0]['state'] == 'authenticated'


def test_upload_resume_idempotency_and_admin_only_download(media):
    api, admin, owner, _, rid, _ = media
    aid = asset(api, owner, rid)
    assert chunk(api, owner, aid).status_code == 200
    assert chunk(api, owner, aid).status_code == 200
    assert chunk(api, owner, aid, b'wrong').status_code == 409
    assert api.get(f'/api/management/assets/{aid}/upload-status', headers=owner).json()['offset'] == 5
    assert api.post(f'/api/management/assets/{aid}/finalize', headers=owner).status_code == 200
    assert api.post(f'/api/management/assets/{aid}/finalize', headers=owner).status_code == 200
    assert api.get(f'/api/management/assets/{aid}/content', headers=owner).status_code == 403
    result = api.get(f'/api/management/assets/{aid}/content', headers=dict(admin, Range='bytes=1-3'))
    assert result.status_code == 206 and result.content == b'edi'
    assert result.headers['content-range'] == 'bytes 1-3/5'
    assert api.get(f'/api/management/assets/{aid}/content', headers=dict(admin, Range='bytes=0-1,3-4')).status_code == 416


def test_foreign_employee_and_bad_chunks(media):
    api, admin, owner, _, rid, _ = media
    uid = employee(api, admin, 'other')
    from app.security import digest
    from app.database import connect_database
    with connect_database(api.app.state.settings.database_path) as db:
        db.execute('INSERT INTO auth_sessions VALUES (?,?,?,NULL)', (digest('other-token'), uid, 9999999999))
    other = {'Authorization': 'Bearer other-token'}
    aid = asset(api, owner, rid)
    assert chunk(api, other, aid).status_code == 404
    assert chunk(api, owner, aid, offset=1).status_code == 409
    assert api.post(f'/api/management/assets/{aid}/finalize', headers=owner).status_code == 409
    assert api.get('/api/management/recordings', headers=owner).status_code == 403
    assert api.get('/console/assets/../../media/private').status_code == 404


def test_checksum_quota_and_capture_event_idempotency(media):
    api, _, owner, _, rid, _ = media
    aid = asset(api, owner, rid)
    assert api.put(f'/api/management/assets/{aid}/chunks/0', headers=dict(owner,
        **{'X-Chunk-SHA256': '0' * 64, 'X-Offset': '0'}), content=b'media').status_code == 422
    event = {'event_id': str(uuid4()), 'stream': 'screen', 'state': 'active', 'offset_ms': 0}
    assert api.post(f'/api/management/recordings/{rid}/events', headers=owner, json=event).status_code == 200
    assert api.post(f'/api/management/recordings/{rid}/events', headers=owner, json=event).status_code == 200
    assert api.post(f'/api/management/recordings/{rid}/events', headers=owner, json=dict(event, state='failed')).status_code == 409
    assert api.post(f'/api/management/recordings/{rid}/assets', headers=owner, json={
        'request_id': str(uuid4()), 'kind': 'screen', 'display_index': 0, 'segment_index': 0,
        'start_offset_ms': 0, 'expected_bytes': 2**31 + 1, 'sha256': '0' * 64, 'format': 'webm'}).status_code == 422
