from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/scripts"))

from acsl_tool.parser import extract_functions, strip_trailing_noise
from acsl_tool import parser


class ParserTest(unittest.TestCase):
    def test_loader_tries_available_candidates_and_caches_success(self) -> None:
        library = mock.Mock()
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(parser, "_LIBCLANG", None), \
             mock.patch.object(parser, "_LIBCLANG_LOAD_ATTEMPTED", False), \
             mock.patch.object(parser, "_LIBCLANG_CANDIDATES", (None, "missing", "available")), \
             mock.patch.object(parser.ctypes, "CDLL", side_effect=[OSError("missing"), library]) as load, \
             mock.patch.object(parser, "_configure_libclang") as configure:
            self.assertIs(parser._load_libclang(), library)
            self.assertIs(parser._load_libclang(), library)
            self.assertEqual(load.call_args_list, [mock.call("missing"), mock.call("available")])
            configure.assert_called_once_with(library)

    def test_explicit_library_path_overrides_discovery(self) -> None:
        with mock.patch.dict(os.environ, {"LIBCLANG_FILE": "/custom/libclang.so"}), \
             mock.patch.object(parser, "_LIBCLANG", None), \
             mock.patch.object(parser, "_LIBCLANG_LOAD_ATTEMPTED", False), \
             mock.patch.object(parser.ctypes, "CDLL") as load, \
             mock.patch.object(parser, "_configure_libclang"):
            self.assertIs(parser._load_libclang(), load.return_value)
            load.assert_called_once_with("/custom/libclang.so")

    def test_missing_or_incompatible_library_reports_prerequisite(self) -> None:
        for failure in (OSError("not installed"), AttributeError("missing Clang API")):
            with self.subTest(failure=failure), \
                 mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(parser, "_LIBCLANG", None), \
                 mock.patch.object(parser, "_LIBCLANG_LOAD_ATTEMPTED", False), \
                 mock.patch.object(parser, "_LIBCLANG_CANDIDATES", ("unusable",)), \
                 mock.patch.object(parser.ctypes, "CDLL", side_effect=failure if isinstance(failure, OSError) else None), \
                 mock.patch.object(parser, "_configure_libclang", side_effect=failure if isinstance(failure, AttributeError) else None):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, "required libclang.*LIBCLANG_FILE"):
                        extract_functions("static inline int helper(void) { return 1; }")

    def test_cli_missing_library_exits_without_overwriting_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = pathlib.Path(tmpdir) / "input.c"
            output = pathlib.Path(tmpdir) / "output.c"
            source.write_text("/*@ assigns \\nothing; */\nint main(void) { return 0; }\n")
            output.write_text("existing output\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "skill/scripts/generate_acsl.py"),
                 str(source), "-o", str(output), "--no-verify-prompt"],
                env={**os.environ, "LIBCLANG_FILE": str(pathlib.Path(tmpdir) / "missing.so")},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("required libclang shared library", result.stderr)
            self.assertIn("LIBCLANG_FILE", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(output.read_text(), "existing output\n")

    def test_extracts_supported_top_level_functions(self) -> None:
        source = """/*@ requires \\true; */
int main()
{
    return helper();
}

char *helper(void)
{
    return 0;
}
"""
        functions = extract_functions(source)
        self.assertEqual([function.name for function in functions], ["main", "helper"])
        self.assertEqual(functions[1].return_type, "char *")

    def test_strip_trailing_noise_removes_prompt_and_repairs_brace(self) -> None:
        source = """/*@ requires \\true; */
int main()
{
    if(1)
    {
        return 0;
dev@host:~/repo$ 
"""
        cleaned = strip_trailing_noise(source)
        self.assertNotIn("dev@host", cleaned)
        self.assertTrue(cleaned.rstrip().endswith("}"))

    def test_static_inline_function_is_supported(self) -> None:
        source = """/*@ requires \\true; */
static inline int helper(void)
{
    return 1;
}
"""
        functions = extract_functions(source)
        self.assertEqual([function.name for function in functions], ["helper"])
        self.assertEqual(functions[0].return_type, "int")


if __name__ == "__main__":
    unittest.main()
