from test_management import env


def test_console_assets_and_security(env):
    client, _, _ = env
    page = client.get('/console')
    assert page.status_code == 200
    assert 'Sasthotech Remote' in page.text
    assert "default-src 'self'" in page.headers['content-security-policy']
    assert page.headers['cache-control'] == 'no-store'
    script = client.get('/console/assets/console.js')
    assert script.status_code == 200
    assert 'localStorage' not in script.text
    assert 'innerHTML' not in script.text
    assert client.get('/console/assets/../app/security.py').status_code == 404
    assert client.get('/api/management/me').status_code == 401
