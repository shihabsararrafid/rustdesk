import shutil
import time

from .database import connect_database
from .media_store import root


def cleanup(settings, apply=False):
    cutoff = time.time() - settings.media_retention_days * 86400
    deleted = []
    with connect_database(settings.database_path) as db:
        db.execute('BEGIN IMMEDIATE')
        records = db.execute("SELECT * FROM recordings WHERE deleted_at IS NULL AND created_at<? "
            "AND (processing_state!='processing' OR processing_lease<?) "
            "AND ((screen_state NOT IN ('starting','active') "
            "AND microphone_state NOT IN ('starting','active')) OR "
            "(updated_at<? AND NOT EXISTS (SELECT 1 FROM media_assets a "
            "WHERE a.recording_id=recordings.id AND a.updated_at>=?)))",
            (cutoff, time.time() - 900, cutoff, cutoff)).fetchall()
        for record in records:
            rid = record['id']
            assets = db.execute('SELECT id FROM media_assets WHERE recording_id=?', (rid,)).fetchall()
            if not apply:
                deleted.append(rid)
                continue
            db.execute('INSERT INTO media_deletions VALUES (?,?,NULL,?)', (rid, time.time(), 'retention_expired'))
            try:
                for asset in assets:
                    path = root(settings) / asset['id']
                    if path.is_symlink():
                        raise OSError('Unexpected media symlink')
                    if path.exists():
                        shutil.rmtree(path)
            except OSError:
                # Persist the attempted deletion, but do not claim it completed.
                continue
            db.execute('UPDATE recordings SET deleted_at=? WHERE id=?', (time.time(), rid))
            db.execute("UPDATE media_assets SET state='expired' WHERE recording_id=?", (rid,))
            db.execute('UPDATE media_deletions SET completed_at=? WHERE recording_id=? AND completed_at IS NULL', (time.time(), rid))
            deleted.append(rid)
    return {'apply': apply, 'recordings': deleted}
