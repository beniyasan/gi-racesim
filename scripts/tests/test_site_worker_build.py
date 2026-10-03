from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "site"))
from build_worker import build_worker  # noqa: E402


class SiteWorkerBuildTests(unittest.TestCase):
    def test_build_contains_static_fallback_and_serves_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dist"
            result = build_worker(ROOT / "apps" / "site", output, source_commit="a" * 40)

            self.assertEqual(result["source_commit"], "a" * 40)
            self.assertTrue((output / "server" / "index.js").is_file())
            self.assertTrue((output / "server" / "worker.js").is_file())
            self.assertTrue((output / ".openai" / "hosting.json").is_file())

            probe = """
import worker from %s;
const root = await worker.fetch(new Request('https://site.test/'), {}, {});
if (root.status !== 200 || !(await root.text()).includes('GIRaceSim')) process.exit(1);
const js = await worker.fetch(new Request('https://site.test/src/app.js'), {}, {});
if (js.status !== 200 || !js.headers.get('content-type').startsWith('text/javascript')) process.exit(2);
""" % json.dumps((output / "server" / "index.js").as_uri())
            subprocess.run(
                ["node", "--input-type=module", "-e", probe],
                check=True,
                cwd=ROOT,
            )


if __name__ == "__main__":
    unittest.main()
