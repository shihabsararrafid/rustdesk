import secrets
import time

from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .database import connect_database
from .security import digest, dummy_hash, hasher

router = APIRouter()


def user_payload(user):
    return {'name': user['username'], 'display_name': user['username'],
            'status': 1, 'is_admin': user['role'] == 'admin',
            'email': '', 'note': '', 'avatar': ''}


def require_user(request: Request):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 1024:
        raise HTTPException(401, 'Authentication required')
    with connect_database(request.app.state.settings.database_path) as db:
        user = db.execute('SELECT u.* FROM users u JOIN auth_sessions s ON u.id=s.user_id '
                          'WHERE s.token_hash=? AND s.expires_at>? AND s.revoked_at IS NULL '
                          'AND u.disabled=0', (digest(header[7:]), time.time())).fetchone()
        if user is None:
            raise HTTPException(401, 'Authentication required')
        return dict(user)


def require_admin(user=Depends(require_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator required')
    return user


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    type: str | None = None


@router.post('/api/login')
def login(body: Login, request: Request):
    settings = request.app.state.settings
    now = time.time()
    limited = False
    with connect_database(settings.database_path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_limits WHERE window_started_at<?', (now - 900,))
        for key, maximum in [('user:' + body.username, 10),
                             ('ip:' + (request.client.host if request.client else 'unknown'), 50)]:
            key = digest(key)
            db.execute('INSERT INTO login_limits VALUES (?,?,1) ON CONFLICT(key_hash) '
                       'DO UPDATE SET attempts=attempts+1', (key, now))
            if db.execute('SELECT attempts FROM login_limits WHERE key_hash=?', (key,)).fetchone()[0] > maximum:
                limited = True
        row = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
    if limited:
        raise HTTPException(429, 'Too many login attempts', headers={'Retry-After': '900'})
    try:
        valid = hasher.verify(row['password_hash'] if row else dummy_hash, body.password)
    except VerificationError:
        valid = False
    if not valid or row is None or row['disabled'] or body.type not in (None, 'account'):
        raise HTTPException(401, 'Invalid credentials')
    token = secrets.token_urlsafe(32)
    with connect_database(settings.database_path) as db:
        db.execute('BEGIN IMMEDIATE')
        # Recheck after expensive hashing so a concurrent reset/disable wins.
        current = db.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
        if current['disabled'] or current['password_hash'] != row['password_hash']:
            raise HTTPException(401, 'Invalid credentials')
        db.execute('DELETE FROM auth_sessions WHERE expires_at<? OR revoked_at IS NOT NULL', (now,))
        db.execute('INSERT INTO auth_sessions VALUES (?,?,?,NULL)',
                   (digest(token), row['id'], now + settings.session_seconds))
    return {'type': 'access_token', 'access_token': token, 'user': user_payload(current)}


@router.post('/api/currentUser')
def current_user(user=Depends(require_user)):
    return user_payload(user)


@router.post('/api/logout')
def logout(request: Request, user=Depends(require_user)):
    with connect_database(request.app.state.settings.database_path) as db:
        db.execute('UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?',
                   (time.time(), digest(request.headers['authorization'][7:])))
    return {'ok': True}


@router.get('/api/login-options')
def login_options():
    return []
