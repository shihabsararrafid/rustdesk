import hashlib
import shutil
import subprocess
from uuid import uuid4

import pytest

from test_recordings import media, asset, chunk
from test_management import env


def test_video_derivative_excludes_remote_audio(media, tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg is required for media processing verification')
    api, admin, owner, _, rid, settings = media
    video = tmp_path / 'fixture.webm'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=64x64:r=10',
                    '-f', 'lavfi', '-i', 'sine=frequency=1000', '-t', '1', '-c:v', 'libvpx', '-c:a', 'libopus', str(video)], check=True)
    data = video.read_bytes()
    aid = asset(api, owner, rid, data)
    assert chunk(api, owner, aid, data).status_code == 200
    assert api.post(f'/api/management/assets/{aid}/finalize', headers=owner).status_code == 200
    for stream in ('screen', 'microphone'):
        if stream == 'screen':
            api.post(f'/api/management/recordings/{rid}/events', headers=owner, json={
                'event_id': str(uuid4()), 'stream': stream, 'state': 'active', 'offset_ms': 0})
        result = api.post(f'/api/management/recordings/{rid}/events', headers=owner, json={
            'event_id': str(uuid4()), 'stream': stream, 'state': 'completed' if stream == 'screen' else 'unavailable',
            'reason': None if stream == 'screen' else 'no_device', 'offset_ms': 1000})
        assert result.status_code == 200
    from app.media_processing import process_once, probe
    from app.media_store import asset_dir
    assert process_once(settings)
    record = api.get('/api/management/recordings', headers=admin).json()['items'][0]
    assert record['processing_state'] == 'ready'
    output = next(a for a in record['assets'] if a['kind'] == 'playback')
    path = asset_dir(settings, output['id']) / 'original.mp4'
    info = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(path)])
    assert b'video' in info and b'audio' not in info


def test_retention_preserves_session_history(media):
    api, admin, owner, sid, rid, settings = media
    from app.database import connect_database
    from app.media_retention import cleanup
    with connect_database(settings.database_path) as db:
        db.execute("UPDATE recordings SET created_at=0,screen_state='failed',microphone_state='unavailable' WHERE id=?", (rid,))
    assert rid in cleanup(settings)['recordings']
    assert api.get('/api/management/recordings', headers=admin).json()['items'][0]['deleted_at'] is None
    assert rid in cleanup(settings, apply=True)['recordings']
    assert api.get('/api/management/reports/sessions', headers=owner).json()['items'][0]['id'] == sid


def test_retention_reclaims_abandoned_reservations_but_preserves_recent_uploads(media):
    api, admin, owner, sid, rid, settings = media
    from app.database import connect_database
    from app.media_retention import cleanup
    aid = asset(api, owner, rid, b'abandoned')
    with connect_database(settings.database_path) as db:
        db.execute('UPDATE recordings SET created_at=0,updated_at=0 WHERE id=?', (rid,))
    assert rid not in cleanup(settings, apply=True)['recordings']
    with connect_database(settings.database_path) as db:
        db.execute('UPDATE media_assets SET updated_at=0 WHERE id=?', (aid,))
    assert rid in cleanup(settings, apply=True)['recordings']
    with connect_database(settings.database_path) as db:
        assert db.execute('SELECT state FROM media_assets WHERE id=?', (aid,)).fetchone()['state'] == 'expired'
