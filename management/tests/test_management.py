import csv
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.database import connect_database, migrate
from app.security import create_user


@pytest.fixture
def env(tmp_path):
    settings = Settings(database_path=str(tmp_path / 'management.db'))
    app = create_app(settings)
    with connect_database(settings.database_path) as db:
        create_user(db, 'admin', 'a-strong-test-password', 'admin')
    with TestClient(app) as client:
        def login(name='admin', password='a-strong-test-password'):
            response = client.post('/api/login', json={'username': name, 'password': password})
            assert response.status_code == 200, response.text
            return {'Authorization': 'Bearer ' + response.json()['access_token']}
        yield client, login, settings


def employee(client, admin, name='employee'):
    response = client.post('/api/management/employees', headers=admin, json={
        'username': name, 'password': 'employee-test-password', 'role': 'employee'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def customer(client, admin):
    response = client.post('/api/management/clients', headers=admin, json={
        'rustdesk_id': '123456789', 'customer_name': 'Hospital', 'device_label': 'Reception'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_database_persistence_and_rollback(env):
    _, _, settings = env
    migrate(settings.database_path)
    with connect_database(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    with pytest.raises(RuntimeError):
        with connect_database(settings.database_path) as db:
            create_user(db, 'rollback', 'long-enough-password', 'employee')
            raise RuntimeError('rollback')
    with connect_database(settings.database_path) as db:
        assert db.execute("SELECT count(*) FROM users WHERE username='rollback'").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO auth_sessions VALUES (?,?,?,NULL)', ('digest', 'missing-user', 1))


def test_login_contract_and_digest_storage(env):
    client, login, settings = env
    assert client.get('/api/login-options').json() == []
    headers = login()
    response = client.post('/api/currentUser', headers=headers, json={})
    assert response.json()['name'] == 'admin'
    assert response.json()['is_admin'] is True
    with connect_database(settings.database_path) as db:
        row = db.execute('SELECT token_hash FROM auth_sessions').fetchone()
        assert headers['Authorization'][7:] != row[0]
    assert client.post('/api/logout', headers=headers).status_code == 200
    assert client.post('/api/currentUser', headers=headers).status_code == 401


def test_roles_disable_reset_and_last_admin(env):
    client, login, _ = env
    admin = login()
    uid = employee(client, admin)
    user = login('employee', 'employee-test-password')
    assert client.get('/api/management/employees', headers=user).status_code == 403
    assert client.post('/api/management/clients', headers=user, json={}).status_code == 403
    assert client.post(f'/api/management/employees/{uid}/password', headers=admin,
                       json={'password': 'another-strong-password'}).status_code == 200
    assert client.post('/api/currentUser', headers=user).status_code == 401
    user = login('employee', 'another-strong-password')
    assert client.patch(f'/api/management/employees/{uid}', headers=admin,
                        json={'disabled': True}).status_code == 200
    assert client.post('/api/currentUser', headers=user).status_code == 401
    aid = client.get('/api/management/employees', headers=admin).json()['items'][0]['id']
    assert client.patch(f'/api/management/employees/{aid}', headers=admin,
                        json={'disabled': True}).status_code == 409


def test_generic_errors_expiry_and_throttle(env):
    client, login, settings = env
    wrong = client.post('/api/login', json={'username': 'admin', 'password': 'incorrect'})
    missing = client.post('/api/login', json={'username': 'missing', 'password': 'incorrect'})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    headers = login()
    with connect_database(settings.database_path) as db:
        db.execute('UPDATE auth_sessions SET expires_at=0')
    assert client.post('/api/currentUser', headers=headers).status_code == 401
    responses = [client.post('/api/login', json={'username': 'missing', 'password': 'incorrect'})
                 for _ in range(12)]
    assert responses[-1].status_code == 429


def test_directory_shared_and_csv_atomic(env):
    client, login, _ = env
    admin = login()
    employee(client, admin, 'one')
    employee(client, admin, 'two')
    customer(client, admin)
    one, two = login('one', 'employee-test-password'), login('two', 'employee-test-password')
    a = client.get('/api/management/clients', headers=one).json()
    assert a == client.get('/api/management/clients', headers=two).json()
    assert a['items'][0]['presence'] == 'unknown'
    bad = 'rustdesk_id,customer_name,device_label,notes\n444,One,Desk,\n444,Two,Desk,\n'
    assert client.post('/api/management/clients/import', headers=admin,
                       content=bad).status_code == 409
    assert client.get('/api/management/clients', headers=admin).json()['total'] == 1
    good = '\ufeffrustdesk_id,customer_name,device_label,notes\n555,"Hospital, East",Desk,"=SUM(1)"\n'
    assert client.post('/api/management/clients/import', headers=admin,
                       content=good.encode()).status_code == 201
    result = client.get('/api/management/clients/export', headers=admin)
    rows = list(csv.DictReader(io.StringIO(result.text)))
    assert rows[1]['notes'].startswith("'=")


def test_audit_lifecycle_idempotency_and_identity(env):
    client, login, settings = env
    admin = login()
    employee(client, admin, 'one')
    employee(client, admin, 'two')
    one, two = login('one', 'employee-test-password'), login('two', 'employee-test-password')
    cid = customer(client, admin)
    body = {'request_id': str(uuid4()), 'client_id': cid, 'mode': 'remote_control'}
    result = client.post('/api/management/sessions', headers=one, json=body)
    assert result.status_code == 201, result.text
    sid = result.json()['id']
    assert client.post('/api/management/sessions', headers=one, json=body).json()['id'] == sid
    forged = dict(body, request_id=str(uuid4()), employee_id='admin')
    assert client.post('/api/management/sessions', headers=one, json=forged).status_code == 422
    url = f'/api/management/sessions/{sid}/events'
    event = {'event_id': str(uuid4()), 'kind': 'authenticated'}
    assert client.post(url, headers=two, json=event).status_code == 404
    assert client.post(url, headers=one, json=event).status_code == 200
    assert client.post(url, headers=one, json=event).status_code == 200
    assert client.post(url, headers=one, json=dict(event, kind='heartbeat')).status_code == 409
    with connect_database(settings.database_path) as db:
        db.execute('UPDATE audit_sessions SET last_seen_at=last_seen_at-121')
    row = client.get('/api/management/reports/sessions', headers=admin).json()['items'][0]
    assert row['state'] == 'interrupted' and row['ended_at'] is None
    assert row['duration_seconds'] is None
    assert row['source'] == 'employee_app_reported'
    closed = {'event_id': str(uuid4()), 'kind': 'closed', 'outcome': 'completed'}
    assert client.post(url, headers=one, json=closed).status_code == 200
    assert client.post(url, headers=one, json={'event_id': str(uuid4()), 'kind': 'authenticated'}).status_code == 409
    assert client.delete(f'/api/management/clients/{cid}', headers=admin).status_code == 409


def test_concurrent_request_id_creates_one_session(env):
    client, login, _ = env
    admin = login()
    cid = customer(client, admin)
    body = {'request_id': str(uuid4()), 'client_id': cid, 'mode': 'file_transfer'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/api/management/sessions',
                                                       headers=admin, json=body), range(4)))
    assert all(r.status_code in (200, 201) for r in responses)
    assert len({r.json()['id'] for r in responses}) == 1


def test_telemetry_gap_does_not_claim_exact_duration(env):
    client, login, settings = env
    admin = login()
    cid = customer(client, admin)
    sid = client.post('/api/management/sessions', headers=admin, json={
        'request_id': str(uuid4()), 'client_id': cid, 'mode': 'remote_control'}).json()['id']
    url = f'/api/management/sessions/{sid}/events'
    client.post(url, headers=admin, json={'event_id': str(uuid4()), 'kind': 'authenticated'})
    with connect_database(settings.database_path) as db:
        db.execute('UPDATE audit_sessions SET last_seen_at=last_seen_at-121')
    client.post(url, headers=admin, json={'event_id': str(uuid4()), 'kind': 'closed', 'outcome': 'completed'})
    row = client.get('/api/management/reports/sessions', headers=admin).json()['items'][0]
    assert row['telemetry_gap'] is True
    assert row['duration_seconds'] is None


def test_limits_reports_and_restart(env):
    client, login, settings = env
    admin = login()
    employee(client, admin)
    user = login('employee', 'employee-test-password')
    cid = customer(client, admin)
    result = client.post('/api/management/sessions', headers=admin, json={
        'request_id': str(uuid4()), 'client_id': cid, 'mode': 'file_transfer'})
    assert result.status_code == 201
    assert client.get('/api/management/reports/sessions', headers=user).json()['total'] == 0
    assert client.get('/api/management/reports/sessions?limit=10000', headers=admin).status_code == 422
    assert client.get('/api/management/reports/sessions?since=2026-01-01T00:00:00', headers=admin).status_code == 422
    assert client.post('/api/management/clients/import', headers=admin,
                       content=b'x' * (settings.max_body_bytes + 1)).status_code == 413
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get('/api/management/reports/sessions', headers=admin).json()['total'] == 1


def test_malformed_and_sensitive_inputs(env):
    client, login, _ = env
    admin = login()
    for data in [b'bad,headers\n1,2', b'\xff',
                 b'rustdesk_id,customer_name,device_label,notes\n123,Name,Desk,secret,extra']:
        assert client.post('/api/management/clients/import', headers=admin, content=data).status_code == 422
    response = client.post('/api/management/employees', headers=admin,
                           json={'username': 'bad', 'password': 'short'})
    assert response.status_code == 422
    assert 'short' not in response.text
    assert client.post('/api/management/clients', headers=admin, json={
        'rustdesk_id': '12', 'customer_name': 'X', 'device_label': 'Y',
        'password': 'remote-password'}).status_code == 422


def test_database_contention_is_bounded(env):
    _, _, settings = env
    with connect_database(settings.database_path) as held:
        held.execute('BEGIN IMMEDIATE')
        db = sqlite3.connect(settings.database_path, timeout=0.02)
        try:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('BEGIN IMMEDIATE')
        finally:
            db.close()


def test_employee_pagination(env):
    client, login, _ = env
    admin = login()
    employee(client, admin, 'one')
    employee(client, admin, 'two')
    first = client.get('/api/management/employees?limit=1&offset=0', headers=admin).json()
    second = client.get('/api/management/employees?limit=1&offset=1', headers=admin).json()
    assert first['total'] == 3 and len(first['items']) == 1
    assert first['items'][0]['id'] != second['items'][0]['id']


def test_oversized_export_is_explicit(env):
    client, login, settings = env
    admin = login()
    with connect_database(settings.database_path) as db:
        db.executemany('INSERT INTO clients VALUES (?,?,?,?,?,?,?)',
                       [(str(uuid4()), str(i), 'Hospital', 'Desk', '', i, i) for i in range(5001)])
    assert client.get('/api/management/clients/export', headers=admin).status_code == 409


@pytest.mark.parametrize('kind', ['failed', 'closed'])
def test_cannot_claim_completed_without_authentication(env, kind):
    client, login, _ = env
    admin = login()
    cid = customer(client, admin)
    sid = client.post('/api/management/sessions', headers=admin, json={
        'request_id': str(uuid4()), 'client_id': cid, 'mode': 'remote_control'}).json()['id']
    assert client.post(f'/api/management/sessions/{sid}/events', headers=admin, json={
        'event_id': str(uuid4()), 'kind': kind, 'outcome': 'completed'}).status_code == 422


def test_chunked_body_limit(env):
    client, login, settings = env
    chunks = (b'x' * 65536 for _ in range(settings.max_body_bytes // 65536 + 1))
    response = client.post('/api/management/clients/import', headers=login(), content=chunks)
    assert response.status_code == 413


def test_conflicting_session_request_and_terminal_failure(env):
    client, login, _ = env
    admin = login()
    cid = customer(client, admin)
    body = {'request_id': str(uuid4()), 'client_id': cid, 'mode': 'file_transfer'}
    sid = client.post('/api/management/sessions', headers=admin, json=body).json()['id']
    conflict = client.post('/api/management/sessions', headers=admin, json=dict(body, mode='remote_control'))
    assert conflict.status_code == 409
    url = f'/api/management/sessions/{sid}/events'
    failure = {'event_id': str(uuid4()), 'kind': 'failed', 'outcome': 'denied'}
    assert client.post(url, headers=admin, json=failure).status_code == 200
    assert client.post(url, headers=admin, json=failure).status_code == 200
    assert client.post(url, headers=admin, json={'event_id': str(uuid4()), 'kind': 'heartbeat'}).status_code == 409
