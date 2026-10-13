"""Define the shared data structures used across parsing, insertion, and verification."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass


@dataclass
class FunctionDef:
    name: str
    return_type: str
    params: str
    signature: str
    start: int
    brace_start: int
    end: int
    body: str
    has_existing_acsl: bool = False


@dataclass
class FunctionAnalysis:
    function: FunctionDef
    category: str
    summary: str
    has_existing_acsl: bool


@dataclass
class AnnotationResult:
    annotated_source: str
    analyses: list[FunctionAnalysis]
    inserted_functions: list[str]


@dataclass
class ContractMetadata:
    source: str | None = None
    source_sha256: str | None = None


@dataclass
class ContractBundle:
    contracts: dict[str, str]
    format_version: str | None = None
    metadata: ContractMetadata | None = None


@dataclass
class VerificationReport:
    command: list[str]
    source_path: pathlib.Path
    exit_code: int
    raw_output: str
    warnings: list[str]
    goals_scheduled: str | None
    proved_goals: str | None
    terminating: str | None
    unreachable: str | None
    qed: str | None
    alt_ergo: str | None
    text_report_path: pathlib.Path
    pdf_report_path: pathlib.Path
    verification_error: str | None = None
