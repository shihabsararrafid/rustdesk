import csv
import io
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import require_admin, require_user
from .employees import database

router = APIRouter(prefix='/api/management/clients', dependencies=[Depends(require_user)])
COLUMNS = ['rustdesk_id', 'customer_name', 'device_label', 'notes']
TARGET_PATTERN = r'^[^\s\x00-\x1f\x7f"<>/\\|?*]{1,253}$'


class Client(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rustdesk_id: str = Field(pattern=TARGET_PATTERN)
    customer_name: str = Field(min_length=1, max_length=200)
    device_label: str = Field(min_length=1, max_length=200)
    notes: str = Field(default='', max_length=2000)


def insert(db, body):
    uid, now = str(uuid4()), time.time()
    db.execute('INSERT INTO clients VALUES (?,?,?,?,?,?,?)',
               (uid, body.rustdesk_id, body.customer_name, body.device_label, body.notes, now, now))
    return uid


@router.get('')
def list_clients(limit: int = 100, offset: int = 0, q: str = '', db=Depends(database)):
    if not 1 <= limit <= 500 or offset < 0:
        raise HTTPException(422, 'Invalid pagination')
    if len(q) > 200:
        raise HTTPException(422, 'Search is too long')
    term = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    where = " WHERE customer_name LIKE ? ESCAPE '\\' OR device_label LIKE ? ESCAPE '\\' OR rustdesk_id LIKE ? ESCAPE '\\'"
    rows = db.execute('SELECT * FROM clients' + where + ' ORDER BY created_at,id LIMIT ? OFFSET ?', (term, term, term, limit, offset))
    return {'items': [dict(r, presence='unknown') for r in rows],
            'total': db.execute('SELECT count(*) FROM clients' + where, (term, term, term)).fetchone()[0]}


@router.post('', status_code=201, dependencies=[Depends(require_admin)])
def add_client(body: Client, db=Depends(database)):
    return {'id': insert(db, body)}


@router.post('/import', status_code=201, dependencies=[Depends(require_admin)])
async def import_clients(request: Request):
    try:
        text = (await request.body()).decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text), strict=True)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Expected exact CSV columns: ' + ','.join(COLUMNS))
        rows = []
        for row in reader:
            if len(rows) >= 5000:
                raise ValueError('Maximum 5000 rows')
            rows.append(Client.model_validate(row))
    except (UnicodeError, csv.Error, ValueError, ValidationError) as exc:
        raise HTTPException(422, 'Invalid UTF-8 CSV or field values') from exc
    # Run blocking database work outside the async request loop.
    from starlette.concurrency import run_in_threadpool
    from .database import connect_database, recheck_authorization

    def save():
        with connect_database(request.app.state.settings.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            recheck_authorization(db, request)
            for row in rows:
                insert(db, row)
        return {'imported': len(rows)}
    return await run_in_threadpool(save)


@router.get('/export', dependencies=[Depends(require_admin)])
def export_clients(db=Depends(database)):
    if db.execute('SELECT count(*) FROM clients').fetchone()[0] > 5000:
        raise HTTPException(409, 'CSV export supports at most 5000 clients; use the paginated directory API')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    for row in db.execute('SELECT * FROM clients ORDER BY created_at,id'):
        values = []
        for column in COLUMNS:
            value = row[column]
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return Response(output.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="clients.csv"'})


@router.put('/{uid}', dependencies=[Depends(require_admin)])
def update_client(uid: str, body: Client, db=Depends(database)):
    result = db.execute('UPDATE clients SET rustdesk_id=?,customer_name=?,device_label=?,notes=?,updated_at=? WHERE id=?',
                        (body.rustdesk_id, body.customer_name, body.device_label, body.notes, time.time(), uid))
    if not result.rowcount:
        raise HTTPException(404, 'Client not found')
    return {'ok': True}


@router.delete('/{uid}', dependencies=[Depends(require_admin)])
def delete_client(uid: str, db=Depends(database)):
    if not db.execute('DELETE FROM clients WHERE id=?', (uid,)).rowcount:
        raise HTTPException(404, 'Client not found')
    return {'ok': True}
