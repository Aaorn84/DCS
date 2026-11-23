CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER PRIMARY KEY, installed_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS records(user_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL, deleted INTEGER NOT NULL, data TEXT NOT NULL, updated DOUBLE PRECISION NOT NULL, PRIMARY KEY(user_id,kind,id));
CREATE TABLE IF NOT EXISTS operations(user_id TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(user_id,id));
CREATE TABLE IF NOT EXISTS rounds(owner TEXT NOT NULL, id TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(owner,id));
CREATE TABLE IF NOT EXISTS receipt_buckets(id BYTEA PRIMARY KEY, owner TEXT NOT NULL, aggregate_id TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(owner,aggregate_id,name));
CREATE TABLE IF NOT EXISTS state_receipts(bucket_id BYTEA NOT NULL REFERENCES receipt_buckets(id), receipt_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(bucket_id,receipt_id));
CREATE TABLE IF NOT EXISTS state_components(owner TEXT NOT NULL, digest TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(owner,digest));
CREATE TABLE IF NOT EXISTS commands(owner TEXT NOT NULL, round_id TEXT NOT NULL, command_id TEXT NOT NULL, digest TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, at DOUBLE PRECISION NOT NULL, seq INTEGER NOT NULL, result TEXT NOT NULL, PRIMARY KEY(owner,round_id,command_id), UNIQUE(owner,round_id,seq), FOREIGN KEY(owner,round_id) REFERENCES rounds(owner,id));
CREATE TABLE IF NOT EXISTS offline_leases(owner TEXT NOT NULL, aggregate_id TEXT NOT NULL, lease_id TEXT NOT NULL UNIQUE, round_id TEXT NOT NULL, device_id TEXT NOT NULL, package TEXT NOT NULL, digest TEXT NOT NULL, base_version INTEGER NOT NULL, cursor INTEGER NOT NULL DEFAULT 0, last_at DOUBLE PRECISION NOT NULL, status TEXT NOT NULL, PRIMARY KEY(owner,aggregate_id));

CREATE TABLE IF NOT EXISTS course_packages(digest TEXT PRIMARY KEY, course_id TEXT NOT NULL, core_version TEXT NOT NULL, payload TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS download_contexts(owner TEXT NOT NULL, digest TEXT NOT NULL, asset_digest TEXT NOT NULL, payload TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(owner,digest));
CREATE TABLE IF NOT EXISTS native_rounds(owner TEXT NOT NULL, round_id TEXT NOT NULL, device_id TEXT NOT NULL, asset_digest TEXT NOT NULL, package_digest TEXT NOT NULL, registration_digest TEXT NOT NULL, course_id TEXT NOT NULL, tee TEXT NOT NULL, memory_allowed BOOLEAN NOT NULL, finished BOOLEAN NOT NULL DEFAULT FALSE, updated_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(owner,round_id));
CREATE INDEX IF NOT EXISTS native_rounds_history ON native_rounds(owner,course_id,tee,finished,updated_at DESC);
CREATE INDEX IF NOT EXISTS native_rounds_profile ON native_rounds(owner,finished,updated_at DESC) WHERE memory_allowed=TRUE;

DELETE FROM schema_meta;
INSERT INTO schema_meta(version) VALUES(3);

ALTER TABLE native_rounds ADD COLUMN IF NOT EXISTS total INTEGER;
ALTER TABLE native_rounds ADD COLUMN IF NOT EXISTS confirmed_holes INTEGER NOT NULL DEFAULT 0;

ALTER TABLE native_rounds ADD COLUMN IF NOT EXISTS started_at DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE native_rounds ADD COLUMN IF NOT EXISTS finished_at DOUBLE PRECISION;
ALTER TABLE native_rounds ADD COLUMN IF NOT EXISTS score_basis TEXT;
CREATE INDEX IF NOT EXISTS native_rounds_occurred ON native_rounds(owner,course_id,tee,finished,started_at DESC);
CREATE TABLE IF NOT EXISTS native_profile_fields(owner TEXT NOT NULL,round_id TEXT NOT NULL,field TEXT NOT NULL,value TEXT NOT NULL,occurred_at DOUBLE PRECISION NOT NULL,event_order INTEGER NOT NULL,PRIMARY KEY(owner,round_id,field));
CREATE INDEX IF NOT EXISTS native_profile_latest ON native_profile_fields(owner,field,occurred_at DESC,event_order DESC,round_id DESC);
