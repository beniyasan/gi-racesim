"""Reject runtime-data/credential paths without rejecting Python package names.

This is a path-based guard, not a general secret/content scanner. Real data must
remain outside the worktree even when its filename does not match these rules.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import subprocess
import sys

RUNTIME_DIRS = frozenset({
    ".local", "data", "raw", "normalized", "datasets", "models", "runs",
    "exports", "logs", "source-artifacts",
})
SENSITIVE_SUFFIXES = (
    ".sqlite", ".sqlite3", ".db", ".parquet", ".har", ".pem", ".key",
    ".p12", ".pfx", ".pt", ".pth", ".ckpt", ".onnx", ".safetensors",
    ".pkl", ".pickle", ".joblib",
)
COMPRESSION_SUFFIXES = (".gz", ".bz2", ".xz", ".zst", ".zip")
SOURCE_ROOT = ("packages", "engine", "src", "gi_racesim")


def violation(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if not parts or PurePosixPath(path).is_absolute() or ".." in parts:
        return "invalid repository-relative path"
    basename = parts[-1].lower()
    if basename == ".env" or (basename.startswith(".env.") and basename not in {
        ".env.example", ".env.sample", ".env.template",
    }):
        return "environment file"
    stem = basename
    while any(stem.endswith(suffix) for suffix in COMPRESSION_SUFFIXES):
        stem = stem.rsplit(".", 1)[0]
    for sidecar in ("-wal", "-shm", "-journal"):
        if stem.endswith(sidecar):
            stem = stem[:-len(sidecar)]
            break
    if stem.endswith(SENSITIVE_SUFFIXES):
        return "runtime database, captured data, model or credential file"
    if any(part.lower() in RUNTIME_DIRS for part in parts[:-1]):
        # Only source modules in the exact code root are exempt. A .parquet or
        # .sqlite below that root is still rejected by the check above.
        if parts[:len(SOURCE_ROOT)] == SOURCE_ROOT and basename.endswith((".py", ".pyi")):
            return None
        return "runtime-data directory"
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Could not inspect tracked files: {error}", file=sys.stderr)
        return 2
    paths = [item.decode("utf-8", "surrogateescape") for item in result.stdout.split(b"\0") if item]
    failures = [(path, reason) for path in paths if (reason := violation(path))]
    for path, reason in failures:
        print(f"REJECT {path!r}: {reason}", file=sys.stderr)
    if failures:
        return 1
    print(f"Tracked-file path guard passed ({len(paths)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
