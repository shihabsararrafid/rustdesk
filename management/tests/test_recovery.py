import json
from pathlib import Path
import subprocess
import sys

from test_management import env


def test_backup_restore_refuses_overwrite(env, tmp_path):
    _, _, settings = env
    script = Path(__file__).resolve().parents[1] / 'deploy/recovery.py'
    backup, restored = tmp_path / 'backup', tmp_path / 'restored'
    subprocess.run([sys.executable, str(script), 'backup', settings.database_path, str(backup)], check=True)
    subprocess.run([sys.executable, str(script), 'verify', str(backup), str(restored)], check=True)
    assert json.loads((backup / 'manifest.json').read_text())['counts']['users'] == 1
    denied = subprocess.run([sys.executable, str(script), 'verify', str(backup), str(restored)], capture_output=True)
    assert denied.returncode != 0
    with (backup / 'management.db').open('ab') as file:
        file.write(b'corrupt')
    assert subprocess.run([sys.executable, str(script), 'verify', str(backup), str(tmp_path / 'other')], capture_output=True).returncode != 0
