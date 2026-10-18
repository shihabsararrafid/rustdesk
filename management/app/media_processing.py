"""Offline, bounded playback derivatives. Original assets are never removed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from .database import connect_database
from .media_store import asset_dir, checksum


def probe(path, format):
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-f', {'wav': 'wav', 'webm': 'matroska', 'mp4': 'mov'}[format],
        '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
        capture_output=True, timeout=30, check=True)
    if len(result.stdout) > 65536:
        raise ValueError('Oversized media metadata')
    data = json.loads(result.stdout)
    duration = float(data.get('format', {}).get('duration', 0))
    if not 0 < duration <= 86400:
        raise ValueError('Unsupported media duration')
    if any(int(s.get('width', 0)) > 8192 or int(s.get('height', 0)) > 8192 for s in data.get('streams', [])):
        raise ValueError('Media dimensions exceed limit')
    expected = 'audio' if format == 'wav' else 'video'
    if not any(s.get('codec_type') == expected for s in data.get('streams', [])):
        raise ValueError('Required media track is missing')
    return duration


def process_once(settings):
    now = time.time()
    with connect_database(settings.database_path) as db:
        db.execute('BEGIN IMMEDIATE')
        # Only one live lease across processes; stale leases are retryable.
        if db.execute("SELECT 1 FROM recordings WHERE processing_state='processing' AND processing_lease>?", (now - 900,)).fetchone():
            return False
        row = db.execute("SELECT * FROM recordings WHERE deleted_at IS NULL AND processing_state IN ('pending','processing') "
            "AND (processing_lease IS NULL OR processing_lease<?) AND screen_state IN ('completed','failed','unavailable') "
            "AND microphone_state IN ('completed','failed','unavailable') ORDER BY created_at LIMIT 1", (now - 900,)).fetchone()
        if not row:
            return False
        rid = row['id']
        db.execute("UPDATE recordings SET processing_state='processing',processing_lease=? WHERE id=?", (now, rid))
        assets = [dict(a) for a in db.execute("SELECT * FROM media_assets WHERE recording_id=? AND state='uploaded' ORDER BY display_index,segment_index", (rid,))]
    try:
        microphone = [a for a in assets if a['kind'] == 'employee_microphone']
        videos = [a for a in assets if a['kind'] == 'screen']
        for audio in microphone:
            probe(asset_dir(settings, audio['id']) / 'original.wav', 'wav')
        for video in videos:
            source = asset_dir(settings, video['id']) / ('original.' + video['format'])
            duration = probe(source, video['format'])
            aid = str(uuid4())
            reserved = min(settings.media_asset_bytes, 2 * 1024**3)
            with connect_database(settings.database_path) as db:
                db.execute('BEGIN IMMEDIATE')
                total = db.execute("SELECT coalesce(sum(expected_bytes),0) FROM media_assets WHERE state NOT IN ('deleted','expired')").fetchone()[0]
                if 2 * (total + reserved) > settings.media_quota_bytes:
                    raise ValueError('Derivative storage quota exceeded')
                db.execute('INSERT INTO media_assets (id,request_id,recording_id,kind,display_index,segment_index,start_offset_ms,expected_bytes,sha256,format,state,created_at,updated_at) '
                    "VALUES (?,?,?,'playback',?,?,?,?,?,'mp4','pending',?,?)",
                    (aid, aid, rid, video['display_index'], video['segment_index'], video['start_offset_ms'], reserved, '0' * 64, now, now))
            target = asset_dir(settings, aid) / 'original.mp4'
            temporary = target.with_name('processing.mp4')
            args = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe',
                    '-f', 'matroska' if video['format'] == 'webm' else 'mov', '-i', str(source)]
            filters, audio_labels = [], []
            for index, audio in enumerate(microphone, 1):
                args += ['-protocol_whitelist', 'file,pipe', '-f', 'wav', '-i', str(asset_dir(settings, audio['id']) / 'original.wav')]
                delta = audio['start_offset_ms'] - video['start_offset_ms']
                label = f'a{index}'
                filters.append(f'[{index}:a:0]atrim=start={max(0,-delta)/1000},asetpts=PTS-STARTPTS,adelay={max(0,delta)}:all=1[{label}]')
                audio_labels.append(f'[{label}]')
            if audio_labels:
                filters.append(''.join(audio_labels) + f'amix=inputs={len(audio_labels)}:normalize=0,apad[audio]')
                args += ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[audio]', '-c:a', 'aac']
            else:
                # Explicitly exclude any remote audio track in the video input.
                args += ['-map', '0:v:0', '-an']
            args += ['-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-threads', '1',
                     '-t', str(duration), '-fs', str(reserved), '-movflags', '+faststart', str(temporary)]
            subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
            actual_duration = probe(temporary, 'mp4')
            if abs(actual_duration - duration) > 1:
                raise ValueError('Playback derivative is truncated')
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            size = target.stat().st_size
            digest = checksum(target)
            with connect_database(settings.database_path) as db:
                db.execute("UPDATE media_assets SET state='uploaded',expected_bytes=?,received_bytes=?,sha256=?,updated_at=? WHERE id=?",
                           (size, size, digest, time.time(), aid))
        with connect_database(settings.database_path) as db:
            db.execute("UPDATE recordings SET processing_state=?,processing_lease=NULL WHERE id=?", ('ready' if videos else 'failed', rid))
        return True
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        with connect_database(settings.database_path) as db:
            db.execute("UPDATE recordings SET processing_state='failed',processing_lease=NULL WHERE id=?", (rid,))
        return True
