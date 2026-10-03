import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFile } from "node:fs/promises";
import { readRun, saveRun } from "../src/storage.js";

globalThis.crypto ??= webcrypto;

function fakeStorage() {
  const rows = new Map();
  const objects = new Map();
  return {
    rows,
    objects,
    DB: {
      prepare(sql) {
        return {
          bind(...values) {
            return {
              async first() {
                if (!sql.startsWith("SELECT")) return null;
                return rows.get(`${values[0]}\0${values[1]}`) ?? null;
              },
              async run() {
                if (rows.has(`${values[0]}\0${values[1]}`)) throw new Error("UNIQUE constraint failed");
                rows.set(`${values[0]}\0${values[1]}`, { content_hash: values[2], object_key: values[3], byte_length: values[4] });
                return { success: true };
              },
            };
          },
        };
      },
    },
    BUCKET: {
      async put(key, bytes) { objects.set(key, new Uint8Array(bytes)); },
      async get(key) {
        const bytes = objects.get(key);
        return bytes ? { arrayBuffer: async () => bytes.slice().buffer } : null;
      },
      async delete(key) { objects.delete(key); },
    },
  };
}

const fixture = await readFile(new URL("../../../contracts/viewer/v1/fixtures/synthetic-race.json", import.meta.url));
const request = (method, body, owner) => new Request("https://site.test/api/runs", { method, body, headers: owner ? { "oai-authenticated-user-id": owner } : {} });

test("requires a platform-authenticated user", async () => {
  const response = await saveRun(request("POST", fixture), fakeStorage());
  assert.equal(response.status, 401);
});

test("persists exact bytes, survives a new request, and isolates owners", async () => {
  const env = fakeStorage();
  const saved = await saveRun(request("POST", fixture, "owner-a"), env);
  assert.equal(saved.status, 201);
  const runId = "run-synthetic-001";
  const loaded = await readRun(new Request(`https://site.test/api/runs/${runId}`, { headers: { "oai-authenticated-user-id": "owner-a" } }), env, runId);
  assert.equal(loaded.status, 200);
  assert.equal(loaded.headers.get("x-content-sha256"), "9070dd48ab3fcbb21fb5da44d3af53235212b69ee3c634d20af4b5afbdb35845");
  assert.deepEqual(new Uint8Array(await loaded.arrayBuffer()), new Uint8Array(fixture));
  const denied = await readRun(new Request(`https://site.test/api/runs/${runId}`, { headers: { "oai-authenticated-user-id": "owner-b" } }), env, runId);
  assert.equal(denied.status, 404);
});

test("rejects a different byte hash for the same owner and run", async () => {
  const env = fakeStorage();
  assert.equal((await saveRun(request("POST", fixture, "owner-a"), env)).status, 201);
  const changed = Buffer.from(fixture);
  changed[changed.length - 1] = 0x20;
  assert.equal((await saveRun(request("POST", changed, "owner-a"), env)).status, 409);
});

test("detects tampering in the stored object", async () => {
  const env = fakeStorage();
  await saveRun(request("POST", fixture, "owner-a"), env);
  const key = [...env.objects.keys()][0];
  env.objects.set(key, new TextEncoder().encode("tampered"));
  const response = await readRun(new Request("https://site.test/api/runs/run-synthetic-001", { headers: { "oai-authenticated-user-id": "owner-a" } }), env, "run-synthetic-001");
  assert.equal(response.status, 500);
});
