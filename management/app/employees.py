import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth import require_admin
from .database import transaction
from .security import create_user, hasher

router = APIRouter(prefix='/api/management/employees', dependencies=[Depends(require_admin)])


class NewEmployee(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,100}$')
    password: str = Field(min_length=12, max_length=256)
    role: Literal['admin', 'employee'] = 'employee'


class Password(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=12, max_length=256)


class EmployeePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    disabled: bool


def database(request: Request):
    yield from transaction(request)


@router.get('')
def list_employees(limit: int = 100, offset: int = 0, db=Depends(database)):
    if not 1 <= limit <= 500 or offset < 0:
        raise HTTPException(422, 'Invalid pagination')
    return {'items': [dict(r) for r in db.execute(
        'SELECT id,username,role,disabled,created_at FROM users ORDER BY created_at,id LIMIT ? OFFSET ?',
        (limit, offset))], 'total': db.execute('SELECT count(*) FROM users').fetchone()[0]}


@router.post('', status_code=201)
def add_employee(body: NewEmployee, db=Depends(database)):
    return {'id': create_user(db, body.username, body.password, body.role)}


@router.patch('/{uid}')
def update_employee(uid: str, body: EmployeePatch, db=Depends(database)):
    row = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Employee not found')
    if body.disabled and row['role'] == 'admin' and not row['disabled']:
        count = db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
        if count <= 1:
            raise HTTPException(409, 'Cannot disable the last administrator')
    db.execute('UPDATE users SET disabled=? WHERE id=?', (body.disabled, uid))
    if body.disabled:
        db.execute('UPDATE auth_sessions SET revoked_at=? WHERE user_id=?', (time.time(), uid))
    return {'ok': True}


@router.post('/{uid}/password')
def reset_password(uid: str, body: Password, db=Depends(database)):
    if db.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone() is None:
        raise HTTPException(404, 'Employee not found')
    db.execute('UPDATE users SET password_hash=? WHERE id=?', (hasher.hash(body.password), uid))
    db.execute('UPDATE auth_sessions SET revoked_at=? WHERE user_id=?', (time.time(), uid))
    return {'ok': True}
