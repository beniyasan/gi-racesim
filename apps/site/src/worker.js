import { readRun, saveRun } from "./storage.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/runs" && request.method === "POST") return saveRun(request, env);
    const match = url.pathname.match(/^\/api\/runs\/([^/]+)$/);
    if (match && request.method === "GET") return readRun(request, env, decodeURIComponent(match[1]));
    if (url.pathname.startsWith("/api/")) return new Response(JSON.stringify({ error: "not_found" }), { status: 404, headers: { "content-type": "application/json" } });
    if (env.ASSETS?.fetch) return env.ASSETS.fetch(request);
    return new Response("Not found", { status: 404 });
  },
};
