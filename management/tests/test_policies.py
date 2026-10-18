import json
from uuid import uuid4

from test_management import env, employee, customer


def test_policy_defaults_overrides_and_mode_authorization(env):
    client, login, settings = env
    admin = login()
    uid = employee(client, admin)
    user = login('employee', 'employee-test-password')
    assert client.get('/api/management/me', headers=user).json()['policy']['allow_clipboard']
    assert client.put('/api/management/policies/company', headers=user,
                      json={'allow_file_transfer': False}).status_code == 403
    assert client.put('/api/management/policies/company', headers=admin,
                      json={'allow_file_transfer': False}).status_code == 200
    payload = {'request_id': str(uuid4()), 'target_id': '555555555', 'mode': 'file_transfer'}
    assert client.post('/api/management/sessions', headers=user, json=payload).status_code == 403
    assert client.get('/api/management/clients', headers=user).json()['total'] == 0
    assert client.put(f'/api/management/policies/employees/{uid}', headers=admin,
                      json={'allow_file_transfer': True}).status_code == 200
    result = client.post('/api/management/sessions', headers=user, json=payload)
    assert result.status_code == 201
    assert result.json()['policy']['allow_file_transfer']
    assert client.post('/api/management/sessions', headers=user, json=payload).json()['id'] == result.json()['id']
    assert client.get('/api/management/clients', headers=user).json()['total'] == 1


def test_policy_unknown_fields_and_camera_terminal(env):
    client, login, _ = env
    admin = login()
    assert client.put('/api/management/policies/company', headers=admin,
                      json={'allow_clipboard': 'false'}).status_code == 422
    assert client.put('/api/management/policies/company', headers=admin,
                      json={'is_admin': True}).status_code == 422
    for mode in ('camera', 'terminal', 'rdp'):
        result = client.post('/api/management/sessions', headers=admin, json={
            'request_id': str(uuid4()), 'target_id': '222', 'mode': mode})
        assert result.status_code == 201, result.text


def test_existing_policy_snapshot_not_reissued_after_policy_change(env):
    client, login, _ = env
    admin = login()
    cid = customer(client, admin)
    payload = {'request_id': str(uuid4()), 'client_id': cid, 'mode': 'remote_control'}
    response = client.post('/api/management/sessions', headers=admin, json=payload)
    assert response.status_code == 201
    assert client.put('/api/management/policies/company', headers=admin,
                      json={'allow_remote_control': False}).status_code == 200
    assert client.post('/api/management/sessions', headers=admin, json=payload).status_code == 403


def test_migration_preserves_version_one_data(tmp_path):
    from pathlib import Path
    from app.database import connect_database, migrate
    from app.security import create_user
    path = str(tmp_path / 'old.db')
    with connect_database(path) as db:
        db.executescript(Path('management/app/migrations/001_initial.sql').read_text())
        create_user(db, 'existing', 'existing-strong-password', 'admin')
        db.execute('PRAGMA user_version=1')
    migrate(path)
    migrate(path)
    with connect_database(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT username FROM users').fetchone()[0] == 'existing'


def test_heartbeat_cannot_mask_missing_authentication(env):
    client, login, _ = env
    headers = login()
    result = client.post('/api/management/sessions', headers=headers, json={
        'request_id': str(uuid4()), 'target_id': '999', 'mode': 'remote_control'})
    url = '/api/management/sessions/' + result.json()['id'] + '/events'
    assert client.post(url, headers=headers, json={'event_id': str(uuid4()), 'kind': 'heartbeat'}).status_code == 409
    assert client.post(url, headers=headers, json={'event_id': str(uuid4()), 'kind': 'closed'}).status_code == 409


def test_existing_direct_and_alternate_server_targets_are_auditable(env):
    client, login, _ = env
    headers = login()
    for target in ('10.0.0.5', 'desktop.example.com:21118', '123@rd.example.com', '[2001:db8::1]:21118'):
        response = client.post('/api/management/sessions', headers=headers, json={
            'request_id': str(uuid4()), 'target_id': target, 'mode': 'remote_control'})
        assert response.status_code == 201, response.text
        assert response.json()['target_id'] == target
