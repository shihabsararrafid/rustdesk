CREATE TABLE recordings (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES audit_sessions(id),
 employee_id TEXT NOT NULL REFERENCES users(id), screen_state TEXT NOT NULL DEFAULT 'starting',
 microphone_state TEXT NOT NULL DEFAULT 'starting', screen_reason TEXT, microphone_reason TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
 processing_state TEXT NOT NULL DEFAULT 'pending', processing_lease REAL,
 UNIQUE(session_id,request_id)
);
CREATE TABLE media_assets (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, recording_id TEXT NOT NULL REFERENCES recordings(id),
 kind TEXT NOT NULL, display_index INTEGER NOT NULL, segment_index INTEGER NOT NULL,
 start_offset_ms INTEGER NOT NULL, expected_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
 format TEXT NOT NULL, received_bytes INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(recording_id,request_id)
);
CREATE TABLE media_chunks (
 asset_id TEXT NOT NULL REFERENCES media_assets(id), chunk_index INTEGER NOT NULL,
 offset INTEGER NOT NULL, length INTEGER NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(asset_id,chunk_index)
);
CREATE TABLE media_events (
 recording_id TEXT NOT NULL REFERENCES recordings(id), event_id TEXT NOT NULL,
 stream TEXT NOT NULL, state TEXT NOT NULL, reason TEXT, offset_ms INTEGER NOT NULL,
 received_at REAL NOT NULL, PRIMARY KEY(recording_id,event_id)
);
CREATE TABLE media_deletions (
 recording_id TEXT NOT NULL REFERENCES recordings(id), requested_at REAL NOT NULL,
 completed_at REAL, reason TEXT NOT NULL
);
CREATE TABLE media_sessions (
 token_hash TEXT PRIMARY KEY, auth_token_hash TEXT NOT NULL REFERENCES auth_sessions(token_hash) ON DELETE CASCADE,
 expires_at REAL NOT NULL
);
CREATE INDEX media_owner ON recordings(employee_id,created_at);
CREATE INDEX media_recording ON media_assets(recording_id);
