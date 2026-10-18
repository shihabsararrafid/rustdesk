import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect_database(path):
    # FastAPI can resume a single request's sync dependency on another worker.
    # Connections remain request-local and are never used concurrently.
    db = sqlite3.connect(path, timeout=5, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def migrate(path):
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with connect_database(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 3:
            raise RuntimeError('Database schema is newer than this service')
        if version == 0:
            sql = Path(__file__).with_name('migrations').joinpath('001_initial.sql').read_text()
            db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=1;\nCOMMIT;')
            version = 1
        if version == 1:
            sql = Path(__file__).with_name('migrations').joinpath('002_employee_policies.sql').read_text()
            db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=2;\nCOMMIT;')
            version = 2
        if version == 2:
            sql = Path(__file__).with_name('migrations').joinpath('003_recordings.sql').read_text()
            db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=3;\nCOMMIT;')
    Path(path).chmod(0o600)


def transaction(request):
    with connect_database(request.app.state.settings.database_path) as db:
        db.execute('BEGIN IMMEDIATE')
        recheck_authorization(db, request)
        yield db


def recheck_authorization(db, request):
    import time
    from fastapi import HTTPException
    from .security import digest
    token = request.headers.get('authorization', '')
    row = db.execute('SELECT u.id FROM users u JOIN auth_sessions s ON u.id=s.user_id '
                     'WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.disabled=0',
                     (digest(token[7:]) if token.startswith('Bearer ') else '', time.time())).fetchone()
    if row is None:
        raise HTTPException(401, 'Authentication required')
