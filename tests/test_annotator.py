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
    def test_raw_override_cannot_insert_executable_code(self) -> None:
        contract = "/*@ ensures \\result == 1; */\nint injected = 7;\n"
        with self.assertRaisesRegex(ValueError, "only ACSL annotations"):
            annotate_source(SOURCE, {"helper": contract})

    def test_line_contracts_on_definitions_and_prototypes_are_preserved(self) -> None:
        for declaration in ("", "extern int main(void);\n"):
            with self.subTest(prototype=bool(declaration)):
                source = "//@ assigns \\nothing;\n//@ ensures \\result == 0;\n" + declaration
                source += "int main(void) { return 0; }\nint helper(void) { return 1; }\n"
                contract = "/*@ ensures \\result == 1; */\n"
                result = annotate_source(source, {"helper": contract})
                self.assertEqual(result.inserted_functions, ["helper"])
                self.assertEqual(result.annotated_source, source.replace("int helper", contract + "int helper"))
                with self.assertRaisesRegex(ValueError, "already have ACSL"):
                    annotate_source(source, {"main": contract, "helper": contract})

    def test_prompt_in_comment_and_final_whitespace_are_preserved(self) -> None:
        source = "/*@ ensures \\result == 0; */\nint main(void) { return 0; }\n"
        source += "/*\nDocumentation transcript:\ndev@host:~/repo$ build\n*/\n"
        source += "int helper(void) { return 1; }\n\n  "
        contract = "/*@ ensures \\result == 1; */\n"
        result = annotate_source(source, {"helper": contract})
        self.assertEqual(result.annotated_source, source.replace("int helper", contract + "int helper"))

    def test_truncated_function_is_rejected_without_brace_repair(self) -> None:
        source = "/*@ ensures \\result == 0; */\nint main(void) { return 0;\n"
        with self.assertRaisesRegex(ValueError, "Unmatched function brace"):
            annotate_source(source, {})

    def test_utf8_comments_preserve_insertion_positions(self) -> None:
        source = "/* café 日本語 */\n" + SOURCE.replace("    return 1;", "    /* naïve */ return 1;")
        contract = "/*@ assigns \\nothing; ensures \\result == 1; */\n"
        result = annotate_source(source, {"helper": contract})
        self.assertEqual(result.annotated_source, source.replace("int helper()", contract + "int helper()"))

    def test_prototype_contract_is_preserved_without_duplicate(self) -> None:
        source = "/*@ ensures \\result == 1; */\nextern int entry(void);\nint entry(void) { return helper(); }\n/* helper description */\nint helper(void) { return 1; }\n"
        result = annotate_source(source, {"helper": "/*@ ensures \\result == 1; */\n"})
        self.assertEqual(result.inserted_functions, ["helper"])
        self.assertTrue(next(a for a in result.analyses if a.function.name == "entry").has_existing_acsl)
        with self.assertRaisesRegex(ValueError, "already have ACSL"):
            annotate_source(source, {"entry": "/*@ ensures 1; */", "helper": "/*@ ensures 1; */"})

    def test_global_predicate_before_prototype_is_not_a_function_contract(self) -> None:
        source = "/*@ predicate ready = \\true; */\nextern int helper(void);\nint helper(void) { return 1; }\n"
        result = annotate_source(source, {"helper": "/*@ ensures \\result == 1; */\n"})
        self.assertEqual(result.inserted_functions, ["helper"])

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
