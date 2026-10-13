from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "measure_codex_contracts.py"
    spec = importlib.util.spec_from_file_location("measure_codex_contracts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MeasureCodexContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_extracts_output_text_from_nested_response(self) -> None:
        response = {
            "model": "gpt-5",
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"format":"acsl-contracts-v2","metadata":{"source":"input/x.c","source_sha256":"abc"},"contracts":{}}',
                        }
                    ]
                }
            ],
        }

        text = self.module.extract_output_text(response)
        self.assertIn('"format":"acsl-contracts-v2"', text)

    def test_parses_markdown_wrapped_json(self) -> None:
        payload = self.module.parse_contract_payload(
            """```json
{"format":"acsl-contracts-v2","metadata":{"source":"input/x.c","source_sha256":"abc"},"contracts":{}}
```"""
        )

        self.assertEqual(payload["format"], "acsl-contracts-v2")
        self.assertEqual(payload["contracts"], {})

    def test_summarizes_usage_fields(self) -> None:
        summary = self.module.summarize_usage(
            {
                "id": "resp_123",
                "model": "gpt-5",
                "usage": {
                    "input_tokens": 321,
                    "output_tokens": 45,
                    "total_tokens": 366,
                    "input_tokens_details": {"cached_tokens": 12},
                    "output_tokens_details": {"reasoning_tokens": 7},
                },
            }
        )

        self.assertEqual(summary["input_tokens"], 321)
        self.assertEqual(summary["output_tokens"], 45)
        self.assertEqual(summary["cached_input_tokens"], 12)
        self.assertEqual(summary["reasoning_output_tokens"], 7)

    def test_build_text_format_can_fallback_to_json_mode(self) -> None:
        self.assertEqual(self.module.build_text_format(use_schema=False), {"type": "json_object"})

        structured = self.module.build_text_format(use_schema=True)
        self.assertEqual(structured["type"], "json_schema")
        self.assertEqual(structured["name"], "acsl_contract_bundle")

    def test_detects_invalid_json_schema_error(self) -> None:
        self.assertTrue(
            self.module.is_invalid_json_schema_error(
                '{"error":{"code":"invalid_json_schema","message":"bad schema"}}'
            )
        )
        self.assertFalse(
            self.module.is_invalid_json_schema_error('{"error":{"code":"rate_limit_exceeded"}}')
        )
        self.assertFalse(self.module.is_invalid_json_schema_error("not json"))


if __name__ == "__main__":
    unittest.main()
