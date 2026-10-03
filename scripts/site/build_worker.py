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
import re
import shutil
import sys
import subprocess
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from package import ALLOWED_FILES, package_site  # noqa: E402


RUNTIME_FILES = ("src/worker.js", "src/storage.js")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


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


def _git_output(repo_root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("selected source commit is not available") from error
    return result.stdout


def _selected_commit(source_root: Path, source_commit: str | None) -> tuple[Path, str]:
    repo_root = Path(_git_output(source_root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    commit = source_commit.lower() if source_commit else _git_output(repo_root, "rev-parse", "HEAD").decode().strip().lower()
    if not SHA1_RE.fullmatch(commit):
        raise ValueError("source commit must be a full lowercase SHA-1")
    _git_output(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    return repo_root, commit


def _regular_file(path: Path, relative: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required source file is not a regular file: {relative}")
    return path.read_bytes()


def _migration_files(repo_root: Path) -> list[str]:
    root = repo_root / "drizzle"
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("drizzle must be a regular directory")
    paths: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(repo_root).as_posix()
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ValueError(f"migration tree contains a non-regular entry: {relative}")
        if path.is_file():
            paths.append(relative)
    return sorted(paths)


def _validate_selected_source(source_root: Path, source_commit: str | None) -> tuple[Path, str, Path, list[str]]:
    """Verify every file copied into the Worker artifact against one commit."""
    repo_root, commit = _selected_commit(source_root, source_commit)
    hosting = _hosting_file(source_root)
    try:
        hosting_relative = hosting.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise ValueError("hosting manifest must be inside the Git repository") from error

    try:
        source_relative = source_root.relative_to(repo_root)
    except ValueError as error:
        raise ValueError("source root must be inside the Git repository") from error

    source_files = [*ALLOWED_FILES, *RUNTIME_FILES]
    paths = {
        (source_relative / relative).as_posix(): source_root / relative
        for relative in source_files
    }
    paths[hosting_relative] = hosting
    current_migrations = _migration_files(repo_root)
    committed_migrations = _git_output(repo_root, "ls-tree", "-r", "--name-only", commit, "--", "drizzle").decode().splitlines()
    committed_migrations = sorted(path for path in committed_migrations if path)
    if current_migrations != committed_migrations:
        raise ValueError("migration files differ from selected source commit")
    for relative in current_migrations:
        paths[relative] = repo_root / relative

    for relative, path in paths.items():
        current = _regular_file(path, relative)
        committed = _git_output(repo_root, "show", f"{commit}:{relative}")
        if current != committed:
            raise ValueError(f"source file differs from selected commit: {relative}")
    return repo_root, commit, hosting, current_migrations


def build_worker(source_root: Path, output: Path, *, source_commit: str | None = None) -> dict[str, object]:
    source_root = source_root.resolve()
    output = output.resolve()
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    if output == source_root or source_root in output.parents:
        raise ValueError("output must be outside the source root")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"refusing to overwrite a non-empty output: {output}")

    _, selected_commit, hosting, migration_files = _validate_selected_source(source_root, source_commit)

    with tempfile.TemporaryDirectory(prefix="gi-racesim-site-package-") as temporary:
        package_dir = Path(temporary) / "package"
        manifest = package_site(source_root, package_dir, source_commit=selected_commit)
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

        hosting_target = output / ".openai" / "hosting.json"
        hosting_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hosting, hosting_target)

    return {
        "output": str(output),
        "source_commit": manifest["source_commit"],
        "package_sha256": manifest["package_sha256"],
        "asset_count": len(_asset_map(output)),
        "migration_count": len(migration_files),
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
