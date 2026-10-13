from __future__ import annotations

import pathlib
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/scripts"))

from acsl_tool.annotator import annotate_source
from acsl_tool.contracts import compute_source_sha256, load_contracts, validate_contract_bundle


SOURCE = """/*@
    assigns g;
*/
void main()
{
    int value;
    value = helper(1);
}

int helper(int x)
{
    if(x == 1)
        return 7;
    return 3;
}
"""


class EndToEndTest(unittest.TestCase):
    def test_cli_handles_crlf_source_and_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="logos path with spaces ") as tmpdir:
            directory = pathlib.Path(tmpdir)
            source = directory / "input file.c"
            contracts = directory / "input contracts.json"
            output = directory / "output file.c"
            original = (
                b"/*@ assigns \\nothing; */\r\nint main(void) { return 0; }\r\n"
                b"static inline int helper(void) { return 1; }\r\n"
            )
            source.write_bytes(original)
            contracts.write_text(json.dumps({
                "format": "acsl-contracts-v2",
                "contracts": {"helper": {"assigns": ["\\nothing"], "ensures": ["\\result == 1"]}},
            }), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "skill/scripts/generate_acsl.py"), str(source),
                 "--contracts", str(contracts), "-o", str(output), "--no-verify-prompt"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            annotated = output.read_text(encoding="utf-8")
            self.assertIn("ensures \\result == 1;", annotated)
            self.assertIn("static inline int helper(void)", annotated)
            self.assertLess(annotated.index("ensures"), annotated.index("static inline"))
            self.assertEqual(source.read_bytes(), original)

    def test_structured_contracts_insert_into_source(self) -> None:
        payload = """{
  "format": "acsl-contracts-v2",
  "metadata": {
    "source": "input/sample.c",
    "source_sha256": "%s"
  },
  "contracts": {
    "helper": {
      "assigns": ["\\\\nothing"],
      "ensures": ["x == 1 ==> \\\\result == 7", "x != 1 ==> \\\\result == 3"]
    }
  }
}
""" % compute_source_sha256(SOURCE)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "contracts.json"
            path.write_text(payload, encoding="utf-8")
            bundle = load_contracts(path)

        self.assertEqual(validate_contract_bundle(bundle, pathlib.Path("input/sample.c"), SOURCE), [])
        result = annotate_source(SOURCE, bundle.contracts)
        self.assertIn("ensures x == 1 ==> \\result == 7;", result.annotated_source)
        self.assertIn("int helper(int x)", result.annotated_source)

    def test_missing_contracts_fail_for_undocumented_functions(self) -> None:
        source = """/*@
    assigns g;
*/
void main()
{
    helper();
}

void helper()
{
    writer();
}

void writer()
{
    g = 1;
}
"""
        with self.assertRaisesRegex(ValueError, "must be authored by Codex"):
            annotate_source(source, {})

    def test_multiple_provided_contracts_insert_into_source(self) -> None:
        source = """/*@
    assigns g;
*/
void main()
{
    helper();
}

void helper()
{
    writer();
}

void writer()
{
    g = 1;
}
"""
        result = annotate_source(
            source,
            {
                "helper": "/*@ assigns \\nothing; */\n",
                "writer": "/*@ assigns g; ensures g == 1; */\n",
            },
        )
        self.assertIn("void helper()", result.annotated_source)
        self.assertIn("assigns \\nothing;", result.annotated_source)
        self.assertIn("ensures g == 1;", result.annotated_source)


if __name__ == "__main__":
    unittest.main()
