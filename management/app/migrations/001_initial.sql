CREATE TABLE users (
 id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','employee')),
 disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)), created_at REAL NOT NULL
);
CREATE TABLE auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 expires_at REAL NOT NULL, revoked_at REAL
);
CREATE TABLE clients (
 id TEXT PRIMARY KEY, rustdesk_id TEXT UNIQUE NOT NULL, customer_name TEXT NOT NULL,
 device_label TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE audit_sessions (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES users(id),
 client_id TEXT NOT NULL REFERENCES clients(id), target_id TEXT NOT NULL, mode TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('attempted','authenticated','failed','closed')),
 started_at REAL NOT NULL, authenticated_at REAL, last_seen_at REAL NOT NULL,
 ended_at REAL, outcome TEXT, telemetry_gap INTEGER NOT NULL DEFAULT 0, UNIQUE(employee_id,request_id)
);
CREATE TABLE audit_events (
 session_id TEXT NOT NULL REFERENCES audit_sessions(id), event_id TEXT NOT NULL,
 kind TEXT NOT NULL, outcome TEXT, received_at REAL NOT NULL, UNIQUE(session_id,event_id)
);
CREATE TABLE login_limits (key_hash TEXT PRIMARY KEY, window_started_at REAL NOT NULL, attempts INTEGER NOT NULL);
CREATE INDEX audit_employee ON audit_sessions(employee_id,started_at);
CREATE INDEX audit_client ON audit_sessions(client_id,started_at);
CREATE INDEX auth_user ON auth_sessions(user_id);
