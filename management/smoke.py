"""Disposable-container HTTP smoke test. Never point at a production database."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

from app.database import connect_database, migrate
from app.security import create_user


def main():
    with tempfile.TemporaryDirectory() as temp:
        path = temp + '/smoke.db'
        migrate(path)
        password = secrets.token_urlsafe(24)
        with connect_database(path) as db:
            create_user(db, 'smoke-admin', password, 'admin')

        def start():
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:create_app',
                                        '--factory', '--host', '127.0.0.1', '--port', '21114',
                                        '--no-access-log', '--no-proxy-headers'],
                                       env=dict(os.environ, MANAGEMENT_DATABASE=path))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('HTTP process exited')
                try:
                    urllib.request.urlopen('http://127.0.0.1:21114/readyz', timeout=1).close()
                    return process
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError('HTTP readiness timed out')

        def request(method, route, data=None, token=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            req = urllib.request.Request('http://127.0.0.1:21114' + route,
                                         data=json.dumps(data).encode() if data is not None else None,
                                         headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)

        process = start()
        try:
            token = request('POST', '/api/login', {'username': 'smoke-admin', 'password': password})['access_token']
            with urllib.request.urlopen('http://127.0.0.1:21114/console', timeout=5) as response:
                assert b'Sasthotech Remote' in response.read()
            employee_password = secrets.token_urlsafe(24)
            for name in ('one', 'two'):
                request('POST', '/api/management/employees', {'username': name, 'password': employee_password}, token)
            one = request('POST', '/api/login', {'username': 'one', 'password': employee_password})['access_token']
            request('PUT', '/api/management/policies/company', {'allow_file_transfer': False}, token)
            assert request('GET', '/api/management/me', token=one)['policy']['allow_file_transfer'] is False
            cid = request('POST', '/api/management/clients', {'rustdesk_id': '123456789',
                          'customer_name': 'Smoke customer', 'device_label': 'Smoke device'}, token)['id']
            sid = request('POST', '/api/management/sessions', {'request_id': str(uuid4()),
                          'client_id': cid, 'mode': 'remote_control'}, one)['id']
            try:
                request('POST', '/api/management/sessions', {'request_id': str(uuid4()),
                        'client_id': cid, 'mode': 'file_transfer'}, one)
                raise AssertionError('Denied policy accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 403
            for kind in ('authenticated', 'closed'):
                request('POST', f'/api/management/sessions/{sid}/events',
                        {'event_id': str(uuid4()), 'kind': kind}, one)
            process.terminate()
            process.wait(timeout=5)
            process = start()
            report = request('GET', '/api/management/reports/sessions', token=token)
            assert report['total'] == 1 and report['items'][0]['state'] == 'closed'
            assert len(request('GET', '/api/management/employees', token=token)['items']) == 3
            print('HTTP login, console, two employees, policy denial, directory, audit lifecycle and restart persistence passed')
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
