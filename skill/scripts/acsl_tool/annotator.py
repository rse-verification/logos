"""Insert provided ACSL contracts into parsed C functions and report what changed."""

from __future__ import annotations

import pathlib

from .contracts import normalize_contract
from .models import AnnotationResult, FunctionAnalysis
from .parser import extract_functions, has_acsl, strip_trailing_noise


def cleanup_legacy_llm_artifacts(output_path: pathlib.Path) -> None:
    for suffix in (".llm-prompt.md", ".llm-context.json", ".llm-contracts.template.json"):
        artifact = output_path.with_suffix(suffix)
        if artifact.exists():
            artifact.unlink()


def _build_analysis(function, has_existing_acsl: bool, has_provided_contract: bool) -> FunctionAnalysis:
    if has_existing_acsl:
        category = "documented"
        summary = "Function already has ACSL and will be preserved."
    else:
        category = "provided-contract"
        summary = "Contract will be inserted from the Codex-authored contracts file."
    return FunctionAnalysis(
        function=function,
        category=category,
        summary=summary,
        has_existing_acsl=has_existing_acsl,
    )


def annotate_source(
    source: str,
    contract_overrides: dict[str, str],
) -> AnnotationResult:
    cleaned = strip_trailing_noise(source)
    if not has_acsl(cleaned):
        raise ValueError("Input file does not contain ACSL markers")

    functions = extract_functions(cleaned)
    function_names = {function.name for function in functions}
    documented_function_names = {
        function.name for function in functions if function.has_existing_acsl
    }
    override_names = set(contract_overrides)
    unknown_overrides = sorted(name for name in override_names if name not in function_names)
    if unknown_overrides:
        raise ValueError(f"Contracts provided for unknown functions: {', '.join(unknown_overrides)}")
    documented_overrides = sorted(name for name in override_names if name in documented_function_names)
    if documented_overrides:
        raise ValueError(
            "Contracts provided for functions that already have ACSL and would not be inserted: "
            + ", ".join(documented_overrides)
        )

    undocumented_function_names = [function.name for function in functions if function.name not in documented_function_names]
    missing_contracts = sorted(name for name in undocumented_function_names if name not in contract_overrides)
    if missing_contracts:
        raise ValueError(
            "Contracts are required for undocumented functions and must be authored by Codex: "
            + ", ".join(missing_contracts)
        )

    analyses = [
        _build_analysis(
            function,
            has_existing_acsl=function.name in documented_function_names,
            has_provided_contract=function.name in contract_overrides,
        )
        for function in functions
    ]

    chunks: list[str] = []
    cursor = 0
    inserted_functions: list[str] = []
    for analysis in analyses:
        function = analysis.function
        chunks.append(cleaned[cursor : function.start])
        if not analysis.has_existing_acsl:
            chunks.append(normalize_contract(contract_overrides[function.name]))
            inserted_functions.append(function.name)
        chunks.append(cleaned[function.start : function.end])
        cursor = function.end
    chunks.append(cleaned[cursor:])

    return AnnotationResult(
        annotated_source="".join(chunks).rstrip() + "\n",
        analyses=analyses,
        inserted_functions=inserted_functions,
    )


def format_analysis_summary(result: AnnotationResult) -> str:
    lines = ["Analysis Summary"]
    for analysis in result.analyses:
        origin = "existing-acsl" if analysis.has_existing_acsl else "provided-contract"
        lines.append(f"- {analysis.function.name}: origin={origin}, summary={analysis.summary}")
    return "\n".join(lines)


def print_generation_summary(
    result: AnnotationResult,
    output_path: pathlib.Path,
    contracts_path: pathlib.Path | None,
) -> None:
    mode = "contracts file" if contracts_path is not None else "missing contracts"
    print("Generation Summary")
    print(f"- Output: {output_path}")
    print(f"- Mode: {mode}")
    print(f"- Contracts inserted: {len(result.inserted_functions)}")
    print(f"- Provided contracts applied: {len(result.inserted_functions)}")
    if contracts_path is not None:
        print(f"- Contracts source: {contracts_path}")
