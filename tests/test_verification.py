from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/scripts"))
from acsl_tool import cli, verification


class VerificationTest(unittest.TestCase):
    def test_wp_requires_complete_nonzero_goals(self):
        for stdout, process_code, passed in (
            ("[wp] Proved goals: 2 / 2\n", 0, True),
            ("[wp] Proved goals: 1 / 2\n", 0, False),
            ("[wp] Proved goals: 0 / 0\n", 0, False),
            ("finished", 0, False),
            ("[wp] Proved goals: 2 / 2\n", 2, False),
            ("Proved goals: 1 / 1\nProved goals: 1 / 2\n", 0, False),
        ):
            with self.subTest(stdout=stdout, process_code=process_code), tempfile.TemporaryDirectory() as tmp:
                source = pathlib.Path(tmp) / "annotated.c"
                source.write_bytes(b"int main(void) { return 0; }\r\n")
                evidence = pathlib.Path(tmp) / "evidence.json"
                options = ["-main", "main", "-wp-rte", "-wp-prover=qed"]
                with mock.patch.object(verification.shutil, "which", return_value="/tools/frama-c"), \
                     mock.patch.object(verification.subprocess, "run", return_value=subprocess.CompletedProcess([], process_code, stdout, "warning")) as run, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = verification.run_framac_wp(source, options, evidence)
                self.assertEqual(code == 0, passed)
                payload = json.loads(evidence.read_text())
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["returncode"], process_code)
                self.assertEqual(payload["verified"], passed)
                self.assertEqual(payload["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(payload["stdout"], stdout)
                self.assertEqual(payload["stderr"], "warning")
                expected = ["/tools/frama-c", *options, "-wp", str(source)]
                self.assertEqual(payload["command"], expected)
                self.assertEqual(run.call_args.args[0], expected)
                self.assertEqual("Status: success" in source.with_suffix(".wp-report.txt").read_text(), passed)
                self.assertTrue(source.with_suffix(".wp-report.pdf").is_file())

    def test_missing_framac_replaces_stale_evidence_with_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "input.c"
            source.write_text("int main(void) { return 0; }")
            evidence = pathlib.Path(tmp) / "verification.json"
            evidence.write_text('{"verified": true}')
            with mock.patch.object(verification.shutil, "which", return_value=None), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(verification.run_framac_wp(source, verification_json=evidence), 0)
            payload = json.loads(evidence.read_text())
            self.assertFalse(payload["verified"])
            self.assertEqual(payload["returncode"], 127)
            self.assertIn("not found", payload["stderr"])

    def test_cli_forwards_options_and_evidence_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "input.c"
            source.write_text("/*@ assigns \\nothing; */\nint main(void) { return 0; }\n")
            output = pathlib.Path(tmp) / "output.c"
            evidence = pathlib.Path(tmp) / "evidence.json"
            argv = ["generate_acsl.py", str(source), "-o", str(output), "--verify",
                    "--verification-json", str(evidence), "--frama-c-option=-main",
                    "--frama-c-option=main", "--frama-c-option=-wp-rte"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(cli, "run_framac_wp", return_value=7) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 7)
            run.assert_called_once_with(output, ["-main", "main", "-wp-rte"], evidence)

    def test_cli_rejects_evidence_without_verification(self):
        with mock.patch.object(sys, "argv", ["generate_acsl.py", "input.c", "--verification-json", "report.json"]), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args()

    def test_cli_rejects_evidence_overwriting_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "input.c"
            source.write_text("/*@ assigns \\nothing; */\nint main(void) { return 0; }\n")
            original = source.read_bytes()
            with mock.patch.object(sys, "argv", ["generate_acsl.py", str(source), "--verify", "--verification-json", str(source)]), \
                 self.assertRaisesRegex(ValueError, "must be separate"):
                cli.main()
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
