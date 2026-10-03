export const MAX_BYTES = 5 * 1024 * 1024;

function json(value, init = {}) {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: { "content-type": "application/json; charset=utf-8", ...(init.headers ?? {}) },
  });
}

export function ownerFromRequest(request) {
  const owner = request.headers.get("oai-authenticated-user-id")?.trim();
  return owner || null;
}

export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireBindings(env) {
  if (!env?.DB || !env?.BUCKET) return json({ error: "storage_unavailable" }, { status: 503 });
  return null;
}

export async function saveRun(request, env) {
  const unavailable = requireBindings(env);
  if (unavailable) return unavailable;
  const owner = ownerFromRequest(request);
  if (!owner) return json({ error: "authentication_required" }, { status: 401 });
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength > MAX_BYTES) return json({ error: "bundle_too_large" }, { status: 413 });
  let bundle;
  try { bundle = JSON.parse(new TextDecoder().decode(bytes)); } catch { return json({ error: "invalid_json" }, { status: 400 }); }
  if (!bundle || typeof bundle !== "object" || Array.isArray(bundle) || typeof bundle.run_id !== "string" || !bundle.run_id) {
    return json({ error: "run_id_required" }, { status: 400 });
  }
  const contentHash = await sha256Hex(bytes);
  const existing = await env.DB.prepare(
    "SELECT content_hash, object_key, byte_length FROM viewer_runs WHERE owner_id = ? AND run_id = ?",
  ).bind(owner, bundle.run_id).first();
  if (existing && existing.content_hash !== contentHash) {
    return json({ error: "run_conflict", expected_hash: existing.content_hash }, { status: 409 });
  }
  const objectKey = existing?.object_key ?? `${owner}/${bundle.run_id}/${contentHash}.json`;
  if (!existing) {
    await env.BUCKET.put(objectKey, bytes, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
    try {
      await env.DB.prepare(
        "INSERT INTO viewer_runs (owner_id, run_id, content_hash, object_key, byte_length, created_at) VALUES (?, ?, ?, ?, ?, ?)",
      ).bind(owner, bundle.run_id, contentHash, objectKey, bytes.byteLength, new Date().toISOString()).run();
    } catch (error) {
      await env.BUCKET.delete(objectKey);
      throw error;
    }
  }
  return json({ run_id: bundle.run_id, content_hash: contentHash, byte_length: bytes.byteLength }, { status: existing ? 200 : 201 });
}

export async function readRun(request, env, runId) {
  const unavailable = requireBindings(env);
  if (unavailable) return unavailable;
  const owner = ownerFromRequest(request);
  if (!owner) return json({ error: "authentication_required" }, { status: 401 });
  const row = await env.DB.prepare(
    "SELECT content_hash, object_key, byte_length FROM viewer_runs WHERE owner_id = ? AND run_id = ?",
  ).bind(owner, runId).first();
  if (!row) return json({ error: "not_found" }, { status: 404 });
  const object = await env.BUCKET.get(row.object_key);
  if (!object) return json({ error: "stored_object_missing" }, { status: 500 });
  const bytes = new Uint8Array(await object.arrayBuffer());
  const actualHash = await sha256Hex(bytes);
  if (actualHash !== row.content_hash || bytes.byteLength !== row.byte_length) {
    return json({ error: "stored_object_hash_mismatch" }, { status: 500 });
  }
  return new Response(bytes, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-sha256": actualHash,
    },
  });
}
