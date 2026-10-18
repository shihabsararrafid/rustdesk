CREATE TABLE company_policy (singleton INTEGER PRIMARY KEY CHECK(singleton=1), settings TEXT NOT NULL);
INSERT INTO company_policy VALUES (1,'{}');
CREATE TABLE employee_policies (employee_id TEXT PRIMARY KEY REFERENCES users(id), settings TEXT NOT NULL);
ALTER TABLE audit_sessions ADD COLUMN policy TEXT NOT NULL DEFAULT '{}';
