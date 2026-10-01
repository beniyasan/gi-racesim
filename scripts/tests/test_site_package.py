import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "site" / "package.py"
spec = importlib.util.spec_from_file_location("site_package", MODULE_PATH)
assert spec and spec.loader
site_package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_package)


class SitePackageTests(unittest.TestCase):
    def test_allowlist_copy_and_manifest_are_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "package"
            manifest = site_package.package_site(
                ROOT / "apps" / "site",
                output,
                source_commit="a" * 40,
            )
            self.assertEqual(manifest["format"], "gi-racesim-site-package/v1")
            self.assertEqual(manifest["source_commit"], "a" * 40)
            self.assertEqual(manifest["source_root"], "apps/site")
            self.assertEqual(
                [entry["path"] for entry in manifest["files"]],
                list(site_package.ALLOWED_FILES),
            )
            stored = json.loads(
                (output / site_package.MANIFEST_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(stored, manifest)
            self.assertEqual(
                sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()),
                sorted((*site_package.ALLOWED_FILES, site_package.MANIFEST_NAME)),
            )

    def test_package_hash_includes_source_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = ROOT / "apps" / "site"
            first = site_package.package_site(source, Path(temporary) / "first", source_commit="a" * 40)
            second = site_package.package_site(source, Path(temporary) / "second", source_commit="b" * 40)
            self.assertNotEqual(first["package_sha256"], second["package_sha256"])

    def test_default_commit_rejects_dirty_source_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            source = repository / "apps" / "site"
            for relative in site_package.ALLOWED_FILES:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=GIRaceSim test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=repository,
                check=True,
            )
            (source / "index.html").write_text("changed", encoding="utf-8")
            with self.assertRaises(site_package.PackageError):
                site_package.package_site(source, Path(temporary) / "out")

    def test_default_commit_rejects_ignored_untracked_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()
            (repository / ".gitignore").write_text("custom-site/\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "add", ".gitignore"], cwd=repository, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=GIRaceSim test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=repository,
                check=True,
            )
            source = repository / "custom-site"
            for relative in site_package.ALLOWED_FILES:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("ignored fixture", encoding="utf-8")
            with self.assertRaises(site_package.PackageError):
                site_package.package_site(source, Path(temporary) / "out")

    def test_custom_source_path_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "custom-site"
            for relative in site_package.ALLOWED_FILES:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            manifest = site_package.package_site(
                source,
                Path(temporary) / "out",
                source_commit="d" * 40,
            )
            self.assertEqual(manifest["source_root"], source.resolve().as_posix())

    def test_unexpected_source_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "site"
            source.mkdir()
            for relative in site_package.ALLOWED_FILES:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            (source / "unexpected.txt").write_text("do not package", encoding="utf-8")
            with self.assertRaises(site_package.PackageError):
                site_package.package_site(source, Path(temporary) / "out", source_commit="b" * 40)

    def test_non_empty_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(site_package.PackageError):
                site_package.package_site(
                    ROOT / "apps" / "site",
                    output,
                    source_commit="c" * 40,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
