from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/scripts"))

from acsl_tool.contracts import compute_source_sha256, load_contracts, normalize_contract, normalize_contract_entry, validate_contract_bundle


class ContractsTest(unittest.TestCase):
    def test_normalizer_accepts_only_annotation_forms_and_code_fences(self) -> None:
        valid = (
            "/*@ ensures \\result == 1; */",
            "//@ assigns \\nothing;\n//@ ensures \\result == 1;",
            "/*@ requires \\true; */\n/*@ ensures \\result == 1; */\n//@ assigns \\nothing;",
            "ensures \\result == 1;",
            "```acsl\n/*@ ensures \\result == 1; */\n```",
            "```c\n//@ ensures \\result == 1;\n```",
        )
        for contract in valid:
            with self.subTest(contract=contract):
                normalized = normalize_contract(contract)
                self.assertTrue(normalized.startswith(("/*@", "//@")))
                self.assertTrue(normalized.endswith("\n"))
                self.assertIn("\\result == 1", normalized)

    def test_normalizer_rejects_executable_code_and_comment_escapes(self) -> None:
        invalid = (
            "/*@ ensures \\result == 1; */\nint injected = 7;\n",
            "ensures \\result == 1; */\nint injected = 7;\n/*@",
            "/*@ requires \\true;",
            "//@ ensures \\result == 1; \\\n",
            "/*@ ensures \\result == 1; *\\\n/ int injected = 7; /*@ assigns \\nothing; */",
        )
        for contract in invalid:
            with self.subTest(contract=contract), self.assertRaises(ValueError):
                normalize_contract(contract)

    def test_structured_contract_fields_cannot_escape_annotations(self) -> None:
        injection = "*/\nint injected = 7;\n/*@"
        for field in ("comments", "requires", "assigns", "ensures", "raw"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "only ACSL annotations"):
                normalize_contract_entry({field: [injection]}, "contracts.helper")

    def test_loads_structured_contract_bundle_with_metadata(self) -> None:
        source = "/*@ requires \\true; */\nint main()\n{\n    return 0;\n}\n"
        payload = """{
  "format": "acsl-contracts-v2",
  "metadata": {
    "source": "input/example.c",
    "source_sha256": "%s"
  },
  "contracts": {
    "helper": {
      "assigns": ["\\\\nothing"],
      "ensures": ["\\\\result == 1"]
    }
  }
}
""" % compute_source_sha256(source)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "contracts.json"
            path.write_text(payload, encoding="utf-8")
            bundle = load_contracts(path)

        self.assertEqual(bundle.format_version, "acsl-contracts-v2")
        self.assertEqual(bundle.metadata.source, "input/example.c")
        self.assertIn("helper", bundle.contracts)
        self.assertIn("assigns \\nothing;", bundle.contracts["helper"])

    def test_warns_when_contract_metadata_is_stale(self) -> None:
        source = "/*@ requires \\true; */\nint main()\n{\n    return 0;\n}\n"
        payload = """{
  "format": "acsl-contracts-v2",
  "metadata": {
    "source": "input/example.c",
    "source_sha256": "%s"
  },
  "contracts": {}
}
""" % ("0" * 64)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "contracts.json"
            path.write_text(payload, encoding="utf-8")
            bundle = load_contracts(path)

        warnings = validate_contract_bundle(bundle, pathlib.Path("input/example.c"), source)
        self.assertTrue(any("stale" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
