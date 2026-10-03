from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "site"))
from build_worker import build_worker  # noqa: E402
from package import ALLOWED_FILES  # noqa: E402


class SiteWorkerBuildTests(unittest.TestCase):
    def test_build_contains_static_fallback_and_serves_all_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            shutil.copytree(ROOT / "apps" / "site", repository / "apps" / "site")
            shutil.copytree(ROOT / "drizzle", repository / "drizzle")
            (repository / ".openai").mkdir(parents=True)
            shutil.copyfile(ROOT / ".openai" / "hosting.json", repository / ".openai" / "hosting.json")
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "user.name=GIRaceSim test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                cwd=repository,
                check=True,
            )
            output = Path(temporary) / "dist"
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            source = repository / "apps" / "site"
            result = build_worker(source, output, source_commit=commit)

            self.assertEqual(result["source_commit"], commit)
            self.assertEqual(result["migration_count"], 1)
            self.assertTrue((output / "server" / "index.js").is_file())
            self.assertTrue((output / "server" / "worker.js").is_file())
            self.assertTrue((output / ".openai" / "hosting.json").is_file())

            probe = """
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import worker from WORKER_URI;
const files = FILES;
for (const relative of files) {
  const response = await worker.fetch(new Request('https://site.test/' + relative), {}, {});
  assert.equal(response.status, 200, relative);
  const expected = await readFile(new URL(relative, SOURCE_URI));
  assert.deepEqual(Buffer.from(await response.arrayBuffer()), expected, relative);
}
const head = await worker.fetch(new Request('https://site.test/', { method: 'HEAD' }), {}, {});
assert.equal(head.status, 200);
assert.equal(await head.text(), '');
assert.equal((await worker.fetch(new Request('https://site.test/', { method: 'POST' }), {}, {})).status, 405);
assert.equal((await worker.fetch(new Request('https://site.test/api/runs', { method: 'POST' }), {}, {})).status, 401);
assert.equal((await worker.fetch(new Request('https://site.test/api/runs/run-1'), {}, {})).status, 401);
for (const path of ['/server/index.js', '/.openai/hosting.json', '/GIRACESIM_SITE_MANIFEST.json', '/missing']) {
  assert.equal((await worker.fetch(new Request('https://site.test' + path), {}, {})).status, 404, path);
}
console.log('worker asset, method, API auth, and 404 checks passed');
""".replace(
                "WORKER_URI", json.dumps((output / "server" / "index.js").as_uri())
            ).replace("FILES", json.dumps(list(ALLOWED_FILES))).replace(
                "SOURCE_URI", json.dumps(source.as_uri() + "/")
            )
            subprocess.run(
                ["node", "--input-type=module", "-e", probe],
                check=True,
                cwd=ROOT,
            )

    def test_dirty_runtime_hosting_and_migration_are_rejected_before_output(self) -> None:
        for relative in (
            Path("apps/site/src/worker.js"),
            Path("apps/site/src/storage.js"),
            Path(".openai/hosting.json"),
            Path("drizzle/0001_viewer_runs.sql"),
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                repository = Path(temporary) / "repo"
                shutil.copytree(ROOT / "apps" / "site", repository / "apps" / "site")
                shutil.copytree(ROOT / "drizzle", repository / "drizzle")
                (repository / ".openai").mkdir(parents=True)
                shutil.copyfile(ROOT / ".openai" / "hosting.json", repository / ".openai" / "hosting.json")
                subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
                subprocess.run(["git", "add", "."], cwd=repository, check=True)
                subprocess.run(
                    ["git", "-c", "user.name=GIRaceSim test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                    cwd=repository,
                    check=True,
                )
                commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
                ).stdout.strip()
                target = repository / relative
                target.write_bytes(target.read_bytes() + b"\nchanged after commit\n")
                output = Path(temporary) / "dist"
                with self.assertRaisesRegex(ValueError, "differs from selected commit|migration files"):
                    build_worker(repository / "apps" / "site", output, source_commit=commit)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
