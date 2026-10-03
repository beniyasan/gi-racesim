#!/usr/bin/env python3
"""Build the Cloudflare Worker artifact for the GIRaceSim Site.

Sites Worker deployments do not provide a static ``ASSETS`` binding unless the
project is a static-only build.  The viewer still needs its reviewed HTML,
JavaScript, stylesheet, schema, fixture, and favicon when it is deployed with
the D1/R2 Worker.  This builder creates a small deterministic asset fallback
around the reviewed Worker source and copies the package manifest alongside it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from package import ALLOWED_FILES, package_site  # noqa: E402


RUNTIME_FILES = ("src/worker.js", "src/storage.js")


def _asset_map(package_dir: Path) -> dict[str, str]:
    assets: dict[str, str] = {}
    for relative in ALLOWED_FILES:
        path = package_dir / relative
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Site asset is not UTF-8 text: {relative}") from error
        key = "/" + relative
        assets[key] = text
        if relative == "index.html":
            assets["/"] = text
    return assets


def _worker_entrypoint(assets: dict[str, str]) -> str:
    # JSON strings are valid JavaScript string literals and ensure that the
    # generated module reproduces each reviewed UTF-8 text asset exactly.
    encoded = json.dumps(assets, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f'''import runtime from "./worker.js";

const STATIC_ASSETS = {encoded};
const CONTENT_TYPES = {{
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
}};

function staticAsset(request) {{
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("Method Not Allowed", {{ status: 405 }});
  let pathname;
  try {{ pathname = decodeURIComponent(new URL(request.url).pathname); }} catch {{ return new Response("Bad Request", {{ status: 400 }}); }}
  const body = STATIC_ASSETS[pathname];
  if (body === undefined) return new Response("Not found", {{ status: 404 }});
  const extension = pathname === "/" ? ".html" : pathname.slice(pathname.lastIndexOf("."));
  return new Response(request.method === "HEAD" ? null : body, {{
    headers: {{
      "cache-control": "no-store",
      "content-type": CONTENT_TYPES[extension] ?? "application/octet-stream",
    }},
  }});
}}

export default {{
  async fetch(request, env, ctx) {{
    const upstreamAssets = env?.ASSETS;
    const assetBinding = {{
      async fetch(assetRequest) {{
        if (typeof upstreamAssets?.fetch === "function") {{
          const response = await upstreamAssets.fetch(assetRequest);
          if (response.status !== 404) return response;
        }}
        return staticAsset(assetRequest);
      }},
    }};
    return runtime.fetch(request, {{ ...env, ASSETS: assetBinding }}, ctx);
  }},
}};
'''


def _hosting_file(source_root: Path) -> Path:
    for parent in (source_root, *source_root.parents):
        candidate = parent / ".openai" / "hosting.json"
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists():
            break
    raise ValueError("missing .openai/hosting.json")


def build_worker(source_root: Path, output: Path, *, source_commit: str | None = None) -> dict[str, object]:
    source_root = source_root.resolve()
    output = output.resolve()
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    if output == source_root or source_root in output.parents:
        raise ValueError("output must be outside the source root")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"refusing to overwrite a non-empty output: {output}")

    with tempfile.TemporaryDirectory(prefix="gi-racesim-site-package-") as temporary:
        package_dir = Path(temporary) / "package"
        manifest = package_site(source_root, package_dir, source_commit=source_commit)
        output.mkdir(parents=True, exist_ok=True)
        for path in package_dir.rglob("*"):
            relative = path.relative_to(package_dir)
            target = output / relative
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)

        server = output / "server"
        server.mkdir(parents=True, exist_ok=True)
        for relative in RUNTIME_FILES:
            target = server / Path(relative).name
            shutil.copyfile(source_root / relative, target)
        (server / "index.js").write_text(_worker_entrypoint(_asset_map(package_dir)), encoding="utf-8")

        hosting = _hosting_file(source_root)
        hosting_target = output / ".openai" / "hosting.json"
        hosting_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hosting, hosting_target)

    return {
        "output": str(output),
        "source_commit": manifest["source_commit"],
        "package_sha256": manifest["package_sha256"],
        "asset_count": len(_asset_map(output)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("apps/site"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    try:
        result = build_worker(args.source, args.output, source_commit=args.source_commit)
    except (OSError, ValueError) as error:
        print(f"worker build failed: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
