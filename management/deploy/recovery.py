"""Consistent SQLite snapshots and non-destructive restore verification."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

TABLES = ('users', 'clients', 'audit_sessions', 'audit_events', 'company_policy', 'employee_policies')


def counts(db):
    return {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in TABLES}


def snapshot(source, destination):
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Snapshot integrity check failed')
            if dst.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Snapshot foreign-key check failed')
            result = counts(dst)
    destination.chmod(0o600)
    return result


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ('backup', 'verify'):
        raise SystemExit('Usage: recovery.py backup|verify SOURCE NEW_DIRECTORY')
    action, source, target = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    if target.exists():
        raise SystemExit('Refusing to overwrite an existing directory')
    os.umask(0o077)
    if action == 'backup':
        if not source.is_file():
            raise SystemExit('Source database does not exist')
        target.mkdir(mode=0o700)
        destination = target / 'management.db'
        totals = snapshot(source, destination)
        manifest = {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'counts': totals}
        (target / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    else:
        manifest = json.loads((source / 'manifest.json').read_text())
        backup = source / 'management.db'
        if hashlib.sha256(backup.read_bytes()).hexdigest() != manifest['sha256']:
            raise SystemExit('Backup checksum mismatch')
        target.mkdir(mode=0o700)
        totals = snapshot(backup, target / 'management.db')
        if totals != manifest['counts']:
            raise SystemExit('Restored row counts differ')
    print(json.dumps({'status': 'verified', 'counts': totals}))


if __name__ == '__main__':
    main()
