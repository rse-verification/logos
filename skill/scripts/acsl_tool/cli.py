"""Parse command-line options and run the ACSL and Frama-C WP workflow."""

from __future__ import annotations

import argparse
import pathlib
import sys

from .annotator import annotate_source, cleanup_legacy_llm_artifacts, format_analysis_summary, print_generation_summary
from .contracts import load_contracts, validate_contract_bundle
from .verification import run_framac_wp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert ACSL contracts into C source and optionally verify them with Frama-C WP."
    )
    parser.add_argument("input", type=pathlib.Path, help="Input C source file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="Output file path")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the input file instead of writing into results/<file>.annotated.c",
    )
    parser.add_argument(
        "--contracts",
        type=pathlib.Path,
        help="JSON file mapping function names to ACSL blocks or structured contract specs",
    )
    parser.add_argument(
        "--llm-contracts",
        dest="contracts",
        type=pathlib.Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run Frama-C WP on the generated file without prompting",
    )
    parser.add_argument(
        "--verification-json", type=pathlib.Path,
        help="Write version-1 verifier evidence for AutoDeduct (requires --verify)",
    )
    parser.add_argument(
        "--frama-c-option", action="append", default=[], metavar="OPTION",
        help="Forward one argument to Frama-C; repeat using --frama-c-option=VALUE",
    )
    parser.add_argument(
        "--no-verify-prompt",
        action="store_true",
        help="Do not ask whether to verify with Frama-C WP after generation",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print a per-function summary of how contracts were chosen",
    )
    args = parser.parse_args()
    if args.verification_json and not args.verify:
        parser.error("--verification-json requires --verify")
    return args


def resolve_output_path(args: argparse.Namespace) -> pathlib.Path:
    if args.in_place:
        return args.input
    if args.output is not None:
        return args.output
    return pathlib.Path("results") / f"{args.input.stem}.annotated.c"


def should_prompt_for_verification(args: argparse.Namespace) -> bool:
    if args.verify or args.no_verify_prompt:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask_to_verify() -> bool:
    answer = input("Do you want to verify it with `frama-c -wp` and save a PDF report? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def main() -> int:
    args = parse_args()
    source = args.input.read_text(encoding="utf-8")
    output_path = resolve_output_path(args)
    if args.verification_json:
        reserved = (args.input, output_path, output_path.with_suffix(".wp-report.txt"),
                    output_path.with_suffix(".wp-report.pdf"), args.contracts)
        if args.verification_json.resolve() in {p.resolve() for p in reserved if p is not None}:
            raise ValueError("--verification-json must be separate from source, contracts, and report files")
        args.verification_json.unlink(missing_ok=True)
    bundle = load_contracts(args.contracts)
    for warning in validate_contract_bundle(bundle, args.input, source):
        print(f"warning: {warning}", file=sys.stderr)
    result = annotate_source(source, bundle.contracts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.annotated_source, encoding="utf-8")
    cleanup_legacy_llm_artifacts(output_path)
    print(f"Wrote output to {output_path}")
    print_generation_summary(result, output_path, args.contracts)
    if args.explain:
        print(format_analysis_summary(result))
    if args.verify:
        return run_framac_wp(output_path, args.frama_c_option, args.verification_json)
    if should_prompt_for_verification(args) and ask_to_verify():
        return run_framac_wp(output_path, args.frama_c_option)
    return 0
