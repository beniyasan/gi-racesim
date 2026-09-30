import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_tracked_files import violation


class TrackedFileGuardTests(unittest.TestCase):
    def test_allows_engine_source_modules(self):
        for path in ("packages/engine/src/gi_racesim/datasets/__init__.py",
                     "packages/engine/src/gi_racesim/datasets/example_builder.py",
                     "packages/engine/src/gi_racesim/models/network.py"):
            with self.subTest(path=path):
                self.assertIsNone(violation(path))

    def test_allows_contracts_and_example_configuration(self):
        for path in ("contracts/viewer/v1/fixtures/synthetic-race.json",
                     "apps/site/src/app.js", "docs/works/WORK-001.md", ".env.example"):
            with self.subTest(path=path):
                self.assertIsNone(violation(path))

    def test_blocks_runtime_directories(self):
        for path in ("raw/page.html", "data/result.json", "runs/result.json",
                     "source-artifacts/input.txt", "exports/result.json",
                     "apps/site/raw/page.html", "datasets/script.py"):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_source_exception_does_not_allow_data(self):
        for path in ("packages/engine/src/gi_racesim/datasets/results.parquet",
                     "packages/engine/src/gi_racesim/datasets/page.html",
                     "packages/engine/src/gi_racesim/models/weights.pt"):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_blocks_sensitive_extensions_anywhere(self):
        for path in ("tmp/crawl.sqlite", "tests/x.db", "tmp/model.safetensors",
                     "docs/private.key", "tmp/capture.har", "tmp/state.pkl"):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_blocks_compressed_data_and_database_sidecars(self):
        for path in ("tmp/capture.har.gz", "tmp/table.parquet.zst", "tmp/key.pem.zip",
                     "tmp/db.sqlite-wal", "tmp/db.sqlite3-shm.gz", "tmp/a.db-journal"):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_blocks_environment_secrets(self):
        for path in (".env", "apps/site/.env.local", ".env.production"):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_blocks_unexpected_root_or_parent_paths(self):
        for path in ("../raw/a.html", "/tmp/code.py", ""):
            with self.subTest(path=path):
                self.assertIsNotNone(violation(path))

    def test_handles_newlines_without_splitting_filename(self):
        self.assertIsNotNone(violation("raw/file\nname.html"))
        self.assertIsNone(violation("docs/file\nname.md"))


if __name__ == "__main__":
    unittest.main()
