"""Load, validate, and render structured contract specifications into ACSL text."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

from .models import ContractBundle, ContractMetadata


def indent_block(lines: list[str]) -> str:
    return "/*@\n" + "\n".join(f"    {line}" if line else "" for line in lines) + "\n  */\n"


def render_assigns_lines(targets: list[str], indent: str = "") -> list[str]:
    if not targets:
        return [f"{indent}assigns \\nothing;"]
    if len(targets) == 1:
        return [f"{indent}assigns {targets[0]};"]
    lines = [f"{indent}assigns {targets[0]},"]
    lines.extend(f"{indent}        {name}," for name in targets[1:-1])
    lines.append(f"{indent}        {targets[-1]};")
    return lines


def extract_assigns_targets(contract: str) -> list[str]:
    match = re.search(r"\bassigns\b(?P<body>[\s\S]*?);", contract)
    if match is None:
        return []
    body = match.group("body")
    targets = [item.strip() for item in body.split(",")]
    return [target for target in targets if target]


def extract_requires_clauses(contract: str) -> list[str]:
    clauses = re.findall(r"\brequires\s+([\s\S]*?);", contract)
    return [clause.strip() for clause in clauses if clause.strip()]


def extract_ensures_clauses(contract: str) -> list[str]:
    clauses = re.findall(r"\bensures\s+([\s\S]*?);", contract)
    return [clause.strip() for clause in clauses if clause.strip()]


def _contract_body_lines(contract: str) -> list[str]:
    body = contract.strip()
    if body.startswith("/*@"):
        body = body[3:]
    if body.endswith("*/"):
        body = body[:-2]
    normalized: list[str] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        normalized.append(stripped)
    return normalized


def extract_behavior_blocks(contract: str) -> list[list[str]]:
    lines = _contract_body_lines(contract)
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("behavior "):
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current and (line.startswith("complete behaviors") or line.startswith("disjoint behaviors")):
            blocks.append(current)
            current = []
            continue
        if current:
            current.append(line)
    if current:
        blocks.append(current)
    return [block for block in blocks if any(item for item in block)]


def extract_behavior_summary_lines(contract: str) -> list[str]:
    return [
        line
        for line in _contract_body_lines(contract)
        if line.startswith("complete behaviors") or line.startswith("disjoint behaviors")
    ]


def normalize_contract(contract: str) -> str:
    stripped = contract.strip()
    stripped = re.sub(r"^```(?:c|acsl)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    stripped = stripped.strip()
    if stripped.startswith("/*@") or stripped.startswith("//@"):
        normalized = stripped + ("\n" if not stripped.endswith("\n") else "")
    else:
        normalized = indent_block([line.rstrip() for line in stripped.splitlines() if line.strip()])
    if normalized.endswith(("\\\n", "\\\r\n")):
        raise ValueError("Contract must not continue its final line into the source with a backslash")
    # C removes backslash-newline pairs before recognizing comments. Check the
    # resulting text so a split block terminator cannot expose executable C.
    comment_text = re.sub(r"\\\r?\n", "", normalized)
    offset = 0
    while offset < len(comment_text):
        if comment_text[offset].isspace():
            offset += 1
        elif comment_text.startswith("/*@", offset):
            end = comment_text.find("*/", offset + 3)
            if end == -1:
                raise ValueError("Contract contains an unterminated ACSL block annotation")
            offset = end + 2
        elif comment_text.startswith("//@", offset):
            end = comment_text.find("\n", offset + 3)
            offset = len(comment_text) if end == -1 else end + 1
        else:
            raise ValueError("Contract text must contain only ACSL annotations and whitespace")
    return normalized


def expect_string_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{context} must be a list of strings")
    return value


def render_behavior_lines(behavior: object, context: str) -> list[str]:
    if not isinstance(behavior, dict):
        raise ValueError(f"{context} must be an object")
    name = behavior.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{context}.name must be a non-empty string")
    allowed = {"name", "assumes", "requires", "assigns", "ensures", "raw"}
    unknown = set(behavior) - allowed
    if unknown:
        raise ValueError(f"{context} has unsupported keys: {', '.join(sorted(unknown))}")
    lines = [f"behavior {name}:"]
    for item in expect_string_list(behavior.get("assumes", []), f"{context}.assumes"):
        lines.append(f"  assumes {item};")
    for item in expect_string_list(behavior.get("requires", []), f"{context}.requires"):
        lines.append(f"  requires {item};")
    if "assigns" in behavior:
        lines.extend(render_assigns_lines(expect_string_list(behavior["assigns"], f"{context}.assigns"), "  "))
    for item in expect_string_list(behavior.get("ensures", []), f"{context}.ensures"):
        lines.append(f"  ensures {item};")
    for item in expect_string_list(behavior.get("raw", []), f"{context}.raw"):
        lines.append(f"  {item}")
    return lines


def render_structured_contract(spec: object, context: str) -> str:
    if not isinstance(spec, dict):
        raise ValueError(f"{context} must be a string or object")
    allowed = {
        "comments",
        "requires",
        "decreases",
        "assigns",
        "ensures",
        "behaviors",
        "complete_behaviors",
        "disjoint_behaviors",
        "raw",
    }
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(f"{context} has unsupported keys: {', '.join(sorted(unknown))}")

    lines: list[str] = []

    comments = expect_string_list(spec.get("comments", []), f"{context}.comments")
    for item in comments:
        lines.append(f"// {item}")
    if comments:
        lines.append("")

    for item in expect_string_list(spec.get("requires", []), f"{context}.requires"):
        lines.append(f"requires {item};")
    if spec.get("requires"):
        lines.append("")

    decreases = spec.get("decreases")
    if decreases is not None:
        if isinstance(decreases, str):
            decreases_items = [decreases]
        else:
            decreases_items = expect_string_list(decreases, f"{context}.decreases")
        for item in decreases_items:
            lines.append(f"decreases {item};")
        lines.append("")

    if "assigns" in spec:
        lines.extend(render_assigns_lines(expect_string_list(spec["assigns"], f"{context}.assigns")))
        lines.append("")

    for item in expect_string_list(spec.get("ensures", []), f"{context}.ensures"):
        lines.append(f"ensures {item};")
    if spec.get("ensures"):
        lines.append("")

    behaviors = spec.get("behaviors", [])
    if behaviors:
        if not isinstance(behaviors, list):
            raise ValueError(f"{context}.behaviors must be a list")
        for index, behavior in enumerate(behaviors):
            lines.extend(render_behavior_lines(behavior, f"{context}.behaviors[{index}]"))
            lines.append("")

    complete = spec.get("complete_behaviors")
    if complete is not None:
        names = expect_string_list(complete, f"{context}.complete_behaviors")
        lines.append(f"complete behaviors {', '.join(names)};")
        lines.append("")

    disjoint = spec.get("disjoint_behaviors")
    if disjoint is not None:
        names = expect_string_list(disjoint, f"{context}.disjoint_behaviors")
        lines.append(f"disjoint behaviors {', '.join(names)};")
        lines.append("")

    for item in expect_string_list(spec.get("raw", []), f"{context}.raw"):
        lines.append(item)

    while lines and not lines[-1]:
        lines.pop()
    return indent_block(lines)


def normalize_contract_entry(contract: object, context: str) -> str:
    if isinstance(contract, str):
        return normalize_contract(contract)
    return normalize_contract(render_structured_contract(contract, context))


def parse_contract_metadata(data: object) -> ContractMetadata | None:
    if not isinstance(data, dict) or "metadata" not in data:
        return None
    metadata = data["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when present")
    allowed = {"source", "source_sha256"}
    unknown = set(metadata) - allowed
    if unknown:
        raise ValueError(f"metadata has unsupported keys: {', '.join(sorted(unknown))}")
    source = metadata.get("source")
    source_sha256 = metadata.get("source_sha256")
    if source is not None and not isinstance(source, str):
        raise ValueError("metadata.source must be a string")
    if source_sha256 is not None:
        if not isinstance(source_sha256, str):
            raise ValueError("metadata.source_sha256 must be a string")
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            raise ValueError("metadata.source_sha256 must be a lowercase SHA-256 hex string")
    return ContractMetadata(source=source, source_sha256=source_sha256)


def compute_source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def validate_contract_bundle(bundle: ContractBundle, source_path: pathlib.Path, source: str) -> list[str]:
    warnings: list[str] = []
    metadata = bundle.metadata
    if metadata is None:
        return warnings
    if metadata.source is not None:
        normalized_actual = source_path.as_posix()
        if metadata.source != normalized_actual:
            warnings.append(
                f"Contracts metadata targets {metadata.source}, but the current source file is {normalized_actual}."
            )
    if metadata.source_sha256 is not None:
        actual_sha256 = compute_source_sha256(source)
        if metadata.source_sha256 != actual_sha256:
            warnings.append(
                "Contracts metadata SHA-256 does not match the current source file. "
                "The contracts may be stale and should be regenerated."
            )
    return warnings


def load_contracts(path: pathlib.Path | None) -> ContractBundle:
    if path is None:
        return ContractBundle(contracts={})
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata = parse_contract_metadata(data)
    format_version = data.get("format") if isinstance(data, dict) else None
    if format_version is not None and not isinstance(format_version, str):
        raise ValueError("format must be a string when present")
    contracts = data["contracts"] if isinstance(data, dict) and "contracts" in data else data
    if not isinstance(contracts, dict):
        raise ValueError("Contracts file must be a JSON object or contain a 'contracts' object")
    normalized: dict[str, str] = {}
    for name, contract in contracts.items():
        if not isinstance(name, str):
            raise ValueError("Each contract entry must use a string function name")
        normalized[name] = normalize_contract_entry(contract, f"contracts.{name}")
    return ContractBundle(contracts=normalized, format_version=format_version, metadata=metadata)
