import time
import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .auth import require_user
from .employees import database
from .policies import effective_policy, check_mode
from .directory import TARGET_PATTERN

router = APIRouter(prefix='/api/management')


class NewSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    client_id: UUID | None = None
    target_id: str | None = Field(default=None, pattern=TARGET_PATTERN)
    mode: Literal['remote_control', 'file_transfer', 'tcp_tunnel', 'rdp', 'terminal', 'camera', 'other']

    @model_validator(mode='after')
    def target(self):
        if (self.client_id is None) == (self.target_id is None):
            raise ValueError('Provide exactly one target')
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID
    kind: Literal['authenticated', 'heartbeat', 'failed', 'closed']
    outcome: Literal['completed', 'denied', 'timeout', 'connection_error', 'cancelled'] | None = None
    telemetry_gap: StrictBool = False


@router.post('/sessions', status_code=201)
def start_session(body: NewSession, user=Depends(require_user), db=Depends(database)):
    policy = effective_policy(db, user['id'])
    check_mode(policy, body.mode)
    row = db.execute('SELECT * FROM audit_sessions WHERE employee_id=? AND request_id=?',
                     (user['id'], str(body.request_id))).fetchone()
    if row:
        if (body.client_id and row['client_id'] != str(body.client_id)) or (body.target_id and row['target_id'] != body.target_id) or row['mode'] != body.mode:
            raise HTTPException(409, 'Request ID reused with different parameters')
        return {'id': row['id'], 'state': row['state'], 'started_at': row['started_at'],
                'employee_id': row['employee_id'], 'target_id': row['target_id'], 'policy': json.loads(row['policy'])}
    if body.target_id:
        client = db.execute('SELECT * FROM clients WHERE rustdesk_id=?', (body.target_id,)).fetchone()
        if client is None:
            from .directory import Client, insert
            uid = insert(db, Client(rustdesk_id=body.target_id, customer_name=body.target_id, device_label=body.target_id))
            client = db.execute('SELECT * FROM clients WHERE id=?', (uid,)).fetchone()
    else:
        client = db.execute('SELECT * FROM clients WHERE id=?', (str(body.client_id),)).fetchone()
    if not client:
        raise HTTPException(404, 'Client not found')
    uid, now = str(uuid4()), time.time()
    db.execute('INSERT INTO audit_sessions '
               '(id,request_id,employee_id,client_id,target_id,mode,state,started_at,last_seen_at,policy) '
               "VALUES (?,?,?,?,?,?,'attempted',?,?,?)",
               (uid, str(body.request_id), user['id'], client['id'], client['rustdesk_id'], body.mode, now, now, json.dumps(policy)))
    return {'id': uid, 'state': 'attempted', 'started_at': now, 'employee_id': user['id'],
            'target_id': client['rustdesk_id'], 'policy': policy}


@router.post('/sessions/{uid}/events')
def session_event(uid: UUID, body: Event, user=Depends(require_user), db=Depends(database)):
    uid = str(uid)
    row = db.execute('SELECT * FROM audit_sessions WHERE id=? AND employee_id=?', (uid, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Session not found')
    existing = db.execute('SELECT * FROM audit_events WHERE session_id=? AND event_id=?',
                          (uid, str(body.event_id))).fetchone()
    if existing:
        if existing['kind'] != body.kind or existing['outcome'] != body.outcome:
            raise HTTPException(409, 'Event ID reused with different parameters')
        return {'ok': True}
    if row['state'] in ('closed', 'failed'):
        raise HTTPException(409, 'Session is terminal')
    if body.kind == 'failed' and row['state'] != 'attempted':
        raise HTTPException(409, 'Authenticated sessions must close')
    if body.kind == 'authenticated' and row['state'] != 'attempted':
        raise HTTPException(409, 'Session already authenticated')
    if body.kind in ('authenticated', 'heartbeat') and body.outcome is not None:
        raise HTTPException(422, 'Non-terminal events cannot have an outcome')
    if body.outcome == 'completed' and (body.kind != 'closed' or row['state'] != 'authenticated'):
        raise HTTPException(422, 'Completion requires a successfully authenticated session')
    if body.kind in ('heartbeat', 'closed') and row['state'] != 'authenticated':
        raise HTTPException(409, 'Authentication must be recorded first')
    now = time.time()
    state = {'authenticated': 'authenticated', 'failed': 'failed', 'closed': 'closed'}.get(body.kind, row['state'])
    gap = bool(row['telemetry_gap']) or now - row['last_seen_at'] > 120 or body.telemetry_gap
    db.execute('UPDATE audit_sessions SET state=?,last_seen_at=?,authenticated_at=?,ended_at=?,outcome=?,telemetry_gap=? WHERE id=?',
               (state, now, now if body.kind == 'authenticated' else row['authenticated_at'],
                now if state in ('closed', 'failed') else None, body.outcome, gap, uid))
    db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)',
               (uid, str(body.event_id), body.kind, body.outcome, now))
    return {'ok': True}


@router.get('/reports/sessions')
def report(user=Depends(require_user), db=Depends(database), limit: int = 100, offset: int = 0,
           employee_id: UUID | None = None, client_id: UUID | None = None,
           state: Literal['attempted', 'authenticated', 'failed', 'closed', 'interrupted'] | None = None,
           since: datetime | None = None, until: datetime | None = None):
    if not 1 <= limit <= 500 or offset < 0:
        raise HTTPException(422, 'Invalid pagination')
    filters, params = [], []
    selected_employee = str(employee_id) if employee_id else None
    if user['role'] != 'admin':
        if selected_employee and selected_employee != user['id']:
            raise HTTPException(403, 'Cannot read another employee report')
        selected_employee = user['id']
    for column, value in [('employee_id', selected_employee), ('client_id', str(client_id) if client_id else None)]:
        if value:
            filters.append(column + '=?')
            params.append(value)
    for stamp, op in [(since, '>='), (until, '<=')]:
        if stamp:
            if stamp.tzinfo is None:
                raise HTTPException(422, 'Dates must contain a timezone')
            filters.append('started_at' + op + '?')
            params.append(stamp.timestamp())
    if since and until and since > until:
        raise HTTPException(422, 'Invalid date range')
    now = time.time()
    effective = "CASE WHEN state IN ('attempted','authenticated') AND last_seen_at<? THEN 'interrupted' ELSE state END"
    if state:
        filters.append('(' + effective + ')=?')
        params.extend([now - 120, state])
    where = ' WHERE ' + ' AND '.join(filters) if filters else ''
    total = db.execute('SELECT count(*) FROM audit_sessions' + where, params).fetchone()[0]
    rows = db.execute('SELECT audit_sessions.*, (SELECT username FROM users WHERE users.id=audit_sessions.employee_id) AS employee_name '
                      'FROM audit_sessions' + where + ' ORDER BY started_at DESC,id LIMIT ? OFFSET ?',
                      (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        if item['state'] in ('attempted', 'authenticated') and item['last_seen_at'] < now - 120:
            item['state'] = 'interrupted'
        item['source'] = 'employee_app_reported'
        item['telemetry_gap'] = bool(item['telemetry_gap']) or item['state'] == 'interrupted'
        item['duration_seconds'] = (item['ended_at'] - item['authenticated_at']
                                    if not item['telemetry_gap'] and item['ended_at'] is not None and item['authenticated_at'] is not None else None)
        items.append(item)
    return {'items': items, 'total': total}
