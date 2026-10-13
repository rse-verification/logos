#!/usr/bin/env python3
"""Generate structured contract JSON with a live model call and record usage metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import textwrap
import urllib.error
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]

SYSTEM_PROMPT = """\
You generate structured ACSL helper contracts for C source files that already contain ACSL.
Return only JSON matching the requested schema.
Do not include markdown fences.
Preserve the existing ACSL style where possible.
Write contracts only for undocumented helper functions.
Prefer concise structured clauses using requires, assigns, ensures, behaviors, complete_behaviors, and disjoint_behaviors.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call a live model to generate contracts/<stem>.contracts.json and save token-usage metadata."
    )
    parser.add_argument("source", type=pathlib.Path, help="Input C source file")
    parser.add_argument("--model", default="gpt-5", help="OpenAI model name to use")
    parser.add_argument(
        "--contracts-out",
        type=pathlib.Path,
        help="Output path for the generated contract JSON (default: contracts/<stem>.contracts.json)",
    )
    parser.add_argument(
        "--usage-out",
        type=pathlib.Path,
        help="Output path for the extracted usage JSON (default: results/<stem>.codex-usage.json)",
    )
    parser.add_argument(
        "--response-out",
        type=pathlib.Path,
        help="Optional path for the raw API response JSON (default: results/<stem>.codex-response.json)",
    )
    parser.add_argument(
        "--response-json",
        type=pathlib.Path,
        help="Parse a previously saved API response JSON instead of making a live network call",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable that holds the API key when making a live call",
    )
    parser.add_argument(
        "--base-url",
        default="https://api.openai.com/v1/responses",
        help="Responses API endpoint",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for the live model call",
    )
    return parser.parse_args()


def compute_source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def default_contracts_path(source: pathlib.Path) -> pathlib.Path:
    return ROOT / "contracts" / f"{source.stem}.contracts.json"


def default_usage_path(source: pathlib.Path) -> pathlib.Path:
    return ROOT / "results" / f"{source.stem}.codex-usage.json"


def default_response_path(source: pathlib.Path) -> pathlib.Path:
    return ROOT / "results" / f"{source.stem}.codex-response.json"


def contract_schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    behavior_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "assumes": string_array,
            "requires": string_array,
            "assigns": string_array,
            "ensures": string_array,
            "raw": string_array,
        },
        "required": ["name", "assumes", "requires", "assigns", "ensures", "raw"],
    }
    contract_spec: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "comments": string_array,
            "requires": string_array,
            "decreases": string_array,
            "assigns": string_array,
            "ensures": string_array,
            "behaviors": {"type": "array", "items": behavior_schema},
            "complete_behaviors": string_array,
            "disjoint_behaviors": string_array,
            "raw": string_array,
        },
        "required": [
            "comments",
            "requires",
            "decreases",
            "assigns",
            "ensures",
            "behaviors",
            "complete_behaviors",
            "disjoint_behaviors",
            "raw",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "format": {"type": "string", "const": "acsl-contracts-v2"},
            "metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "source_sha256": {"type": "string"},
                },
                "required": ["source", "source_sha256"],
            },
            "contracts": {
                "type": "object",
                "additionalProperties": contract_spec,
            },
        },
        "required": ["format", "metadata", "contracts"],
    }


def build_text_format(*, use_schema: bool) -> dict[str, Any]:
    if not use_schema:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": "acsl_contract_bundle",
        "strict": True,
        "schema": contract_schema(),
    }


def build_user_prompt(source_path: pathlib.Path, source_text: str) -> str:
    return textwrap.dedent(
        f"""\
        Read the following C source file and generate structured ACSL helper contracts.

        Requirements:
        - The output must match the requested JSON schema exactly.
        - Reuse the existing ACSL style already present in the source.
        - Include entries only for undocumented helper functions that need contracts.
        - Set metadata.source to "{source_path.as_posix()}".
        - Set metadata.source_sha256 to "{compute_source_sha256(source_text)}".
        - If a contract uses decreases, encode it as an array of strings even for one item.
        - For every contract object, include all schema keys and use empty arrays when a field is not needed.
        - For every behavior object, include all schema keys and use empty arrays when a field is not needed.
        - Do not include any prose outside the JSON object.

        Source file: {source_path.as_posix()}

        ```c
        {source_text}
        ```
        """
    )


def extract_output_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text)
                continue
            if isinstance(text, dict):
                value = text.get("value")
                if isinstance(value, str) and value.strip():
                    chunks.append(value)
                    continue
    if chunks:
        return "\n".join(chunks)
    raise ValueError("response does not contain textual output")


def strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_contract_payload(text: str) -> dict[str, Any]:
    return json.loads(strip_markdown_fences(text))


def summarize_usage(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}

    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    cached_tokens = None
    reasoning_tokens = None
    if isinstance(input_details, dict):
        cached_tokens = input_details.get("cached_tokens")
    if isinstance(output_details, dict):
        reasoning_tokens = output_details.get("reasoning_tokens")

    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": cached_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "model": response.get("model"),
        "response_id": response.get("id"),
    }


def load_response_from_file(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_invalid_json_schema_error(body: str) -> bool:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False

    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") == "invalid_json_schema"


def perform_api_request(
    *,
    api_key: str,
    base_url: str,
    payload: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def make_live_request(
    *,
    source_path: pathlib.Path,
    source_text: str,
    model: str,
    api_key_env: str,
    base_url: str,
    timeout_s: float,
) -> dict[str, Any]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"{api_key_env} is not set")

    base_payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": build_user_prompt(source_path, source_text)}],
            },
        ],
    }

    try:
        return perform_api_request(
            api_key=api_key,
            base_url=base_url,
            payload={**base_payload, "text": {"format": build_text_format(use_schema=True)}},
            timeout_s=timeout_s,
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and is_invalid_json_schema_error(body):
            print(
                "Structured output schema rejected by the Responses API; retrying with json_object mode.",
                file=sys.stderr,
            )
            try:
                return perform_api_request(
                    api_key=api_key,
                    base_url=base_url,
                    payload={**base_payload, "text": {"format": build_text_format(use_schema=False)}},
                    timeout_s=timeout_s,
                )
            except urllib.error.HTTPError as fallback_exc:
                fallback_body = fallback_exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"OpenAI API error {fallback_exc.code}: {fallback_body}") from fallback_exc
            except urllib.error.URLError as fallback_exc:
                raise RuntimeError(f"OpenAI API request failed: {fallback_exc}") from fallback_exc
        raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def ensure_parent(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    source_text = source_path.read_text(encoding="utf-8")

    contracts_out = args.contracts_out or default_contracts_path(source_path)
    usage_out = args.usage_out or default_usage_path(source_path)
    response_out = args.response_out or default_response_path(source_path)

    if args.response_json is not None:
        response = load_response_from_file(args.response_json)
    else:
        response = make_live_request(
            source_path=source_path.relative_to(ROOT) if source_path.is_relative_to(ROOT) else source_path,
            source_text=source_text,
            model=args.model,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            timeout_s=args.timeout_s,
        )
        ensure_parent(response_out)
        response_out.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = parse_contract_payload(extract_output_text(response))

    ensure_parent(contracts_out)
    ensure_parent(usage_out)
    contracts_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    usage_out.write_text(json.dumps(summarize_usage(response), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    usage = summarize_usage(response)
    print(f"Wrote contracts to {contracts_out}")
    print(f"Wrote usage to {usage_out}")
    if args.response_json is None:
        print(f"Wrote raw response to {response_out}")
    print(
        "Usage Summary\n"
        f"- Model: {usage.get('model', 'unknown')}\n"
        f"- Input tokens: {usage.get('input_tokens', 'unknown')}\n"
        f"- Output tokens: {usage.get('output_tokens', 'unknown')}\n"
        f"- Cached input tokens: {usage.get('cached_input_tokens', 'unknown')}\n"
        f"- Total tokens: {usage.get('total_tokens', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
