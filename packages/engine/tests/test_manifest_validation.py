"""Regression tests for PR #1's manifest hash review."""
import copy
import hashlib
import unittest

from gi_racesim.datasets.example_builder import freeze_manifest


class ManifestValidationTests(unittest.TestCase):
    def freeze(self, sources):
        return freeze_manifest(sources=sources, splits={"train": ["r1"]},
                               parser_version="p1", feature_version="f1")

    def test_rejects_non_hex_64_character_hash(self):
        for value in ("x" * 64, "g" * 64, "０" * 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.freeze([{"source_id": "s", "sha256": value}])

    def test_rejects_non_string_hashes_with_value_error(self):
        for value in (None, 123, True, ["a"] * 64, {str(i): i for i in range(64)}, b"a" * 64):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                self.freeze([{"source_id": "s", "sha256": value}])

    def test_rejects_whitespace_and_wrong_length(self):
        for value in ("", "a" * 63, "a" * 65, "a" * 64 + "\n", " " + "a" * 63, "a" * 32 + " " + "a" * 31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.freeze([{"source_id": "s", "sha256": value}])

    def test_rejects_missing_hash(self):
        with self.assertRaises(ValueError):
            self.freeze([{"source_id": "s"}])

    def test_accepts_actual_hexdigest(self):
        value=hashlib.sha256(b"synthetic source").hexdigest()
        self.assertEqual(self.freeze([{"source_id": "s", "sha256": value}])["sources"][0]["sha256"], value)

    def test_canonicalizes_hex_case_without_mutating_input(self):
        upper=[{"source_id": "s", "sha256": "ABCDEF01" * 8}]
        original=copy.deepcopy(upper)
        lower=[{"source_id": "s", "sha256": "abcdef01" * 8}]
        self.assertEqual(self.freeze(upper), self.freeze(lower))
        self.assertEqual(upper, original)

    def test_rejects_invalid_source_ids(self):
        for value in (None, "", "  ", 1, ["s"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.freeze([{"source_id": value, "sha256": "a" * 64}])

    def test_rejects_non_mapping_source(self):
        for value in (None, "s", []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.freeze([value])

    def test_input_metadata_changes_do_not_mutate_snapshot(self):
        sources=[{"source_id": "s", "sha256": "a" * 64, "meta": {"tags": ["original"]}}]
        frozen=self.freeze(sources)
        expected=copy.deepcopy(frozen)
        sources[0]["sha256"]="b" * 64
        sources[0]["meta"]["tags"].append("later")
        self.assertEqual(frozen, expected)

    def test_source_order_is_canonical(self):
        sources=[{"source_id": "b", "sha256": "b" * 64}, {"source_id": "a", "sha256": "a" * 64}]
        self.assertEqual(self.freeze(sources), self.freeze(list(reversed(sources))))


if __name__ == "__main__":
    unittest.main()
