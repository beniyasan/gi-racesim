#!/usr/bin/env python3
"""Create an auditable, allowlisted package for the GIRaceSim Site source.

The package is deliberately a directory rather than an archive.  Sites
support and source-root behavior must be checked in the actual UI, and a
directory keeps the exact files and manifest inspectable before that step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable


PACKAGE_FORMAT = "gi-racesim-site-package/v1"
MANIFEST_NAME = "GIRACESIM_SITE_MANIFEST.json"
ALLOWED_FILES = (
    "index.html",
    "src/app.js",
    "src/content-hash.js",
    "src/styles.css",
    "src/validator.js",
    "public/favicon.svg",
    "public/schema.json",
    "public/fixtures/synthetic-race.json",
)
# These files are reviewed source but are intentionally not sent to the Site
# runtime.  Keeping them explicit makes a newly added source file fail closed.
SOURCE_ONLY_FILES = (
    "package.json",
    "tests/assets.test.mjs",
    "tests/content-hash.test.mjs",
    "tests/storage.test.mjs",
    "tests/validator.test.mjs",
    "src/storage.js",
    "src/worker.js",
)
EXPECTED_SOURCE_FILES = frozenset((*ALLOWED_FILES, *SOURCE_ONLY_FILES))
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class PackageError(ValueError):
    """Raised when a source tree or output directory is unsafe to package."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_root(root: Path) -> Path:
    try:
        repo_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PackageError("source commit could not be determined") from error
    repo_root = Path(repo_result.stdout.strip()).resolve()
    return repo_root


def _source_commit(root: Path, files: Iterable[str]) -> str:
    files = tuple(files)
    repo_root = _git_root(root)
    try:
        relative_source = root.resolve().relative_to(repo_root)
    except ValueError as error:
        raise PackageError("source must be inside its Git repository") from error

    repository_files = [
        (relative_source / relative).as_posix()
        for relative in files
    ]
    tracked_result = subprocess.run(
        ["git", "ls-files", "--cached", "-z", "--", *repository_files],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tracked = {
        path.decode("utf-8")
        for path in tracked_result.stdout.split(b"\0")
        if path
    }
    missing = sorted(set(repository_files) - tracked)
    if missing:
        raise PackageError("source files are not tracked at HEAD: " + ", ".join(missing))

    for relative, repository_file in zip(files, repository_files):
        try:
            head_result = subprocess.run(
                ["git", "show", f"HEAD:{repository_file}"],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise PackageError(f"source file is unavailable at HEAD: {repository_file}") from error
        if (root / relative).read_bytes() != head_result.stdout:
            raise PackageError(
                f"source file differs from HEAD: {repository_file}; "
                "pass a reviewed source commit explicitly"
            )

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PackageError("source commit could not be determined") from error
    commit = result.stdout.strip().lower()
    if not SHA1_RE.fullmatch(commit):
        raise PackageError("source commit is not a full SHA-1")
    return commit


def _source_label(root: Path) -> str:
    """Return a truthful, portable label for the supplied source directory."""
    try:
        repo_root = _git_root(root)
        return root.resolve().relative_to(repo_root).as_posix() or "."
    except (PackageError, ValueError):
        return root.as_posix()


def _validate_source(root: Path, files: Iterable[str]) -> list[tuple[str, bytes]]:
    root = root.resolve()
    if not root.is_dir():
        raise PackageError(f"source root is not a directory: {root}")
    selected: list[tuple[str, bytes]] = []
    for relative in files:
        path = root / relative
        try:
            path.relative_to(root)
        except ValueError as error:
            raise PackageError(f"file escapes source root: {relative}") from error
        if path.is_symlink() or not path.is_file():
            raise PackageError(f"required source file is not a regular file: {relative}")
        selected.append((relative, path.read_bytes()))

    expected = {root / relative for relative in EXPECTED_SOURCE_FILES}
    unexpected = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path not in expected
    )
    if unexpected:
        raise PackageError("unexpected source files: " + ", ".join(unexpected))
    symlinks = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink()
    )
    if symlinks:
        raise PackageError("symlinks are not allowed in the source tree: " + ", ".join(symlinks))
    return selected


def _package_hash(manifest: dict[str, object]) -> str:
    """Hash all package metadata and file entries except this self-reference."""
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(canonical)


def package_site(
    source_root: Path,
    output: Path,
    *,
    source_commit: str | None = None,
) -> dict[str, object]:
    """Copy the allowlisted Site source and return the written manifest."""
    source_root = source_root.resolve()
    output = output.resolve()
    if output == source_root or source_root in output.parents:
        raise PackageError("output must not be inside the source root")
    if output.exists() and not output.is_dir():
        raise PackageError(f"output is not a directory: {output}")
    if output.is_dir() and any(output.iterdir()):
        raise PackageError(f"refusing to overwrite a non-empty output: {output}")

    selected = _validate_source(source_root, ALLOWED_FILES)
    commit = source_commit.lower() if source_commit else _source_commit(
        source_root,
        [relative for relative, _ in selected],
    )
    if not SHA1_RE.fullmatch(commit):
        raise PackageError("source commit must be a full lowercase SHA-1")

    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for relative, data in selected:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append({"path": relative, "bytes": len(data), "sha256": _sha256(data)})

    manifest: dict[str, object] = {
        "format": PACKAGE_FORMAT,
        "source_root": _source_label(source_root),
        "source_commit": commit,
        "files": entries,
    }
    manifest["package_sha256"] = _package_hash(manifest)
    (output / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("apps/site"),
        help="Site source directory (default: apps/site)",
    )
    parser.add_argument("--output", type=Path, required=True, help="new or empty output directory")
    parser.add_argument(
        "--source-commit",
        help="full source Git SHA; omitted means resolve HEAD from the repository root",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = package_site(args.source, args.output, source_commit=args.source_commit)
    except PackageError as error:
        print(f"package failed: {error}")
        return 2
    print(json.dumps({"output": str(args.output.resolve()), **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
