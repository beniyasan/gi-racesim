import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("D1 migration binds ownership and run identity", async () => {
  const sql = await readFile(new URL("../../../drizzle/0001_viewer_runs.sql", import.meta.url), "utf8");
  assert.match(sql, /PRIMARY KEY \(owner_id, run_id\)/);
  assert.match(sql, /content_hash TEXT NOT NULL/);
  assert.match(sql, /object_key TEXT NOT NULL/);
});
