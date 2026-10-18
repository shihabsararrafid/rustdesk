import hashlib
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

CHUNK_BYTES = 1024 * 1024


def root(settings):
    path = Path(settings.media_root) if settings.media_root else Path(settings.database_path).parent / 'media'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError('Media root must not be a symlink')
    return path


def asset_dir(settings, asset_id):
    # asset_id is always a validated/server-generated UUID, never a filename.
    path = root(settings) / str(asset_id)
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError('Media directory must not be a symlink')
    return path


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_bytes(path, data):
    temporary = path.with_name('tmp-' + str(uuid4()))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_chunk(db, settings, row, index, offset, digest, data):
    if not data or len(data) > CHUNK_BYTES:
        raise HTTPException(413, 'Chunk must contain 1 to 1048576 bytes')
    if hashlib.sha256(data).hexdigest() != digest:
        raise HTTPException(422, 'Chunk checksum mismatch')
    existing = db.execute('SELECT * FROM media_chunks WHERE asset_id=? AND chunk_index=?', (row['id'], index)).fetchone()
    if existing:
        if (existing['offset'], existing['length'], existing['sha256']) != (offset, len(data), digest):
            raise HTTPException(409, 'Conflicting chunk retry')
        return {'offset': row['received_bytes']}
    if row['state'] == 'uploaded':
        raise HTTPException(409, 'Asset already finalized')
    if row['state'] not in ('pending', 'uploading'):
        raise HTTPException(409, 'Asset is unavailable')
    count = db.execute('SELECT count(*) FROM media_chunks WHERE asset_id=?', (row['id'],)).fetchone()[0]
    if index != count or offset != row['received_bytes'] or offset + len(data) > row['expected_bytes']:
        raise HTTPException(409, 'Unexpected chunk offset or length')
    path = asset_dir(settings, row['id']) / f'{index}.chunk'
    if path.exists():
        if path.stat().st_size != len(data) or checksum(path) != digest:
            raise HTTPException(409, 'Unacknowledged chunk differs; restart this asset')
    else:
        atomic_bytes(path, data)
    db.execute('INSERT INTO media_chunks VALUES (?,?,?,?,?)', (row['id'], index, offset, len(data), digest))
    db.execute("UPDATE media_assets SET received_bytes=?,state='uploading',updated_at=? WHERE id=?",
               (offset + len(data), time.time(), row['id']))
    return {'offset': offset + len(data)}


def finalize(db, settings, row):
    directory = asset_dir(settings, row['id'])
    path = directory / ('original.' + row['format'])
    if row['state'] == 'uploaded':
        if not path.is_file() or path.stat().st_size != row['expected_bytes']:
            raise HTTPException(503, 'Finalized asset is missing')
        return {'state': 'uploaded'}
    if row['state'] not in ('pending', 'uploading') or row['received_bytes'] != row['expected_bytes']:
        raise HTTPException(409, 'Upload is incomplete or unavailable')
    temporary = directory / ('finalizing-' + str(uuid4()))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        total, digest = 0, hashlib.sha256()
        with os.fdopen(fd, 'wb') as out:
            for chunk in db.execute('SELECT * FROM media_chunks WHERE asset_id=? ORDER BY chunk_index', (row['id'],)):
                piece = directory / f"{chunk['chunk_index']}.chunk"
                data = piece.read_bytes()
                if len(data) != chunk['length'] or hashlib.sha256(data).hexdigest() != chunk['sha256']:
                    raise HTTPException(409, 'Stored chunk failed verification')
                out.write(data)
                digest.update(data)
                total += len(data)
            out.flush()
            os.fsync(out.fileno())
        if total != row['expected_bytes'] or digest.hexdigest() != row['sha256']:
            raise HTTPException(422, 'Final asset checksum mismatch')
        os.replace(temporary, path)
        db.execute("UPDATE media_assets SET state='uploaded',updated_at=? WHERE id=?", (time.time(), row['id']))
        # Chunks remain until a later reconciliation confirms the DB commit.
        return {'state': 'uploaded'}
    finally:
        temporary.unlink(missing_ok=True)
