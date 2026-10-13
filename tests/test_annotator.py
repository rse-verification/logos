from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/scripts"))

from acsl_tool.annotator import annotate_source, format_analysis_summary


SOURCE = """/*@
    assigns g;
*/
void main()
{
    helper();
}

int helper()
{
    return 1;
}
"""


class AnnotatorTest(unittest.TestCase):
    def test_rejects_unknown_override_function(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown functions"):
            annotate_source(SOURCE, {"missing": "/*@ assigns \\nothing; */\n"})

    def test_rejects_missing_contract_for_undocumented_function(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be authored by Codex"):
            annotate_source(SOURCE, {})

    def test_rejects_override_for_already_documented_function(self) -> None:
        documented = """/*@
    assigns \\nothing;
*/
int helper()
{
    return 1;
}
"""
        with self.assertRaisesRegex(ValueError, "already have ACSL"):
            annotate_source(documented, {"helper": "/*@ assigns \\nothing; */\n"})

    def test_formats_analysis_summary(self) -> None:
        result = annotate_source(SOURCE, {"helper": "/*@ assigns \\nothing; */\n"})
        summary = format_analysis_summary(result)
        self.assertIn("helper", summary)
        self.assertIn("origin=provided-contract", summary)
        self.assertIn("main", summary)


if __name__ == "__main__":
    unittest.main()
