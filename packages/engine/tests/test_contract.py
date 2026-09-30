import json
import tempfile
import unittest
from pathlib import Path

from gi_racesim.common.contract import ContractError, bundle_sha256, read_bundle, validate_bundle
from gi_racesim.exporter.bundle import write_bundle


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "viewer" / "v1" / "fixtures" / "synthetic-race.json"


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.bundle = read_bundle(FIXTURE)

    def test_fixture_is_valid(self):
        self.assertEqual(self.bundle["schema_version"], "viewer/v1")
        self.assertEqual(self.bundle["origin"], "synthetic")

    def test_packaged_schema_matches_contract_schema(self):
        packaged = Path(__import__("gi_racesim.common", fromlist=["__file__"]).__file__).with_name("viewer-schema.json")
        self.assertEqual(json.loads(packaged.read_text()), json.loads((ROOT / "contracts/viewer/v1/schema.json").read_text()))

    def test_unknown_schema_rejected(self):
        broken = dict(self.bundle, schema_version="viewer/v2")
        with self.assertRaises(ContractError):
            validate_bundle(broken)

    def test_missing_provenance_rejected(self):
        broken = dict(self.bundle)
        broken.pop("model_id")
        with self.assertRaises(ContractError):
            validate_bundle(broken)

    def test_rank_interval_must_be_ordered(self):
        broken = json.loads(json.dumps(self.bundle))
        broken["simulation"]["representative_trials"][0]["corners"][0]["groups"][0]["members"] = []
        with self.assertRaises(ContractError):
            validate_bundle(broken)

    def test_hash_is_stable_and_export_is_atomic(self):
        first = bundle_sha256(self.bundle)
        second = bundle_sha256(json.loads(json.dumps(self.bundle)))
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = write_bundle(self.bundle, Path(directory) / "result.json")
            self.assertEqual(read_bundle(path), self.bundle)


if __name__ == "__main__":
    unittest.main()
