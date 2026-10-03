CREATE TABLE IF NOT EXISTS viewer_runs (
  owner_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  object_key TEXT NOT NULL,
  byte_length INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (owner_id, run_id)
);
