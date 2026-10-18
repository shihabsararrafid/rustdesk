import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from .auth import require_admin, require_user, user_payload
from .employees import database

router = APIRouter(prefix='/api/management')


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allow_remote_control: StrictBool | None = None
    allow_file_transfer: StrictBool | None = None
    allow_clipboard: StrictBool | None = None
    allow_tcp_tunnel: StrictBool | None = None
    allow_terminal: StrictBool | None = None
    allow_camera: StrictBool | None = None


def effective_policy(db, employee_id):
    policy = dict.fromkeys(PolicyPatch.model_fields, True)
    policy.update(json.loads(db.execute('SELECT settings FROM company_policy WHERE singleton=1').fetchone()[0]))
    row = db.execute('SELECT settings FROM employee_policies WHERE employee_id=?', (employee_id,)).fetchone()
    if row:
        policy.update(json.loads(row['settings']))
    return policy


def check_mode(policy, mode):
    field = {'remote_control': 'allow_remote_control', 'file_transfer': 'allow_file_transfer',
             'tcp_tunnel': 'allow_tcp_tunnel', 'rdp': 'allow_tcp_tunnel',
             'terminal': 'allow_terminal', 'camera': 'allow_camera'}.get(mode)
    if field is None or not policy[field]:
        raise HTTPException(403, 'Connection mode is not permitted by employee policy')


@router.get('/me')
def me(user=Depends(require_user), db=Depends(database)):
    return {'id': user['id'], 'user': user_payload(user), 'role': user['role'],
            'policy': effective_policy(db, user['id']), 'scope': 'managed_employee_app'}


@router.get('/policies', dependencies=[Depends(require_admin)])
def policies(db=Depends(database)):
    return {'company': json.loads(db.execute('SELECT settings FROM company_policy WHERE singleton=1').fetchone()[0]),
            'employees': {r['employee_id']: json.loads(r['settings']) for r in db.execute('SELECT * FROM employee_policies')}}


@router.put('/policies/company', dependencies=[Depends(require_admin)])
def company_policy(body: PolicyPatch, db=Depends(database)):
    values = body.model_dump(exclude_none=True)
    db.execute('UPDATE company_policy SET settings=? WHERE singleton=1', (json.dumps(values),))
    return {'ok': True}


@router.put('/policies/employees/{uid}', dependencies=[Depends(require_admin)])
def employee_policy(uid: str, body: PolicyPatch, db=Depends(database)):
    if not db.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone():
        raise HTTPException(404, 'Employee not found')
    db.execute('INSERT INTO employee_policies VALUES (?,?) ON CONFLICT(employee_id) DO UPDATE SET settings=excluded.settings',
               (uid, json.dumps(body.model_dump(exclude_none=True))))
    return {'ok': True}
