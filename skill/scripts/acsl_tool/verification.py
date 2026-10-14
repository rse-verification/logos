"""Run Frama-C WP and format its output into persistent verification reports."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

from .models import VerificationReport


def parse_metric(output: str, pattern: str) -> str | None:
    matches = list(re.finditer(pattern, output, flags=re.MULTILINE))
    if not matches:
        return None
    match = matches[-1]
    return " ".join(part for part in match.groups() if part is not None).strip()


def resolve_report_paths(source_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    return source_path.with_suffix(".wp-report.txt"), source_path.with_suffix(".wp-report.pdf")


def build_verification_report(
    command: list[str],
    source_path: pathlib.Path,
    exit_code: int,
    raw_output: str,
    verification_error: str | None = None,
) -> VerificationReport:
    text_report_path, pdf_report_path = resolve_report_paths(source_path)
    warnings = re.findall(r"^\[wp\] Warning: (.+)$", raw_output, flags=re.MULTILINE)
    return VerificationReport(
        command=command,
        source_path=source_path,
        exit_code=exit_code,
        raw_output=raw_output.strip(),
        warnings=warnings,
        goals_scheduled=parse_metric(raw_output, r"^\[wp\]\s+(\d+)\s+goals scheduled$"),
        proved_goals=parse_metric(raw_output, r"^\[wp\] Proved goals:\s+(\d+\s*/\s*\d+)$"),
        terminating=parse_metric(raw_output, r"^\s*Terminating:\s+(.+)$"),
        unreachable=parse_metric(raw_output, r"^\s*Unreachable:\s+(.+)$"),
        qed=parse_metric(raw_output, r"^\s*Qed:\s+(.+)$"),
        alt_ergo=parse_metric(raw_output, r"^\s*Alt-Ergo.*:\s+(.+)$"),
        text_report_path=text_report_path,
        pdf_report_path=pdf_report_path,
        verification_error=verification_error or wp_failure(exit_code, raw_output),
    )


def format_terminal_report(report: VerificationReport) -> str:
    status = f"failed: {report.verification_error}" if report.verification_error else "success"
    lines = [
        "",
        "Verification Report",
        f"- Source: {report.source_path}",
        f"- Command: {' '.join(report.command)}",
        f"- Status: {status}",
    ]
    if report.goals_scheduled:
        lines.append(f"- Goals scheduled: {report.goals_scheduled}")
    if report.proved_goals:
        lines.append(f"- Proved goals: {report.proved_goals}")
    if report.terminating:
        lines.append(f"- Terminating: {report.terminating}")
    if report.unreachable:
        lines.append(f"- Unreachable: {report.unreachable}")
    if report.qed:
        lines.append(f"- Qed: {report.qed}")
    if report.alt_ergo:
        lines.append(f"- Alt-Ergo: {report.alt_ergo}")
    if report.warnings:
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    lines.append(f"- Text report: {report.text_report_path}")
    lines.append(f"- PDF report: {report.pdf_report_path}")
    return "\n".join(lines)


def format_full_report(report: VerificationReport) -> str:
    generated_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    status = f"failed: {report.verification_error}" if report.verification_error else "success"
    lines = [
        "Frama-C WP Verification Report",
        "==============================",
        f"Generated at: {generated_at}",
        f"Source file: {report.source_path}",
        f"Command: {' '.join(report.command)}",
        f"Status: {status}",
    ]
    if report.goals_scheduled:
        lines.append(f"Goals scheduled: {report.goals_scheduled}")
    if report.proved_goals:
        lines.append(f"Proved goals: {report.proved_goals}")
    if report.terminating:
        lines.append(f"Terminating: {report.terminating}")
    if report.unreachable:
        lines.append(f"Unreachable: {report.unreachable}")
    if report.qed:
        lines.append(f"Qed: {report.qed}")
    if report.alt_ergo:
        lines.append(f"Alt-Ergo: {report.alt_ergo}")
    if report.warnings:
        lines.extend(["", "Warnings", "--------", *report.warnings])
    lines.extend(["", "Raw Frama-C Output", "------------------", report.raw_output or "(no output captured)", ""])
    return "\n".join(lines)


def write_text_report(report: VerificationReport, content: str) -> None:
    report.text_report_path.parent.mkdir(parents=True, exist_ok=True)
    report.text_report_path.write_text(content, encoding="utf-8")


def escape_pdf_text(line: str) -> str:
    sanitized = line.encode("latin-1", "replace").decode("latin-1")
    return sanitized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_bytes(text: str) -> bytes:
    lines = text.splitlines() or [""]
    page_width = 612
    page_height = 792
    left_margin = 50
    top_margin = 760
    font_size = 10
    leading = 14
    max_lines_per_page = 48
    page_chunks = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)]
    objects: list[bytes] = []
    page_object_numbers: list[int] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    font_obj = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_obj_placeholder = add_object(b"")
    for chunk in page_chunks:
        stream_lines = ["BT", f"/F1 {font_size} Tf", f"{left_margin} {top_margin} Td", f"{leading} TL"]
        for index, line in enumerate(chunk):
            escaped = escape_pdf_text(line)
            if index == 0:
                stream_lines.append(f"({escaped}) Tj")
            else:
                stream_lines.append(f"T* ({escaped}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        content_obj = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )
        page_obj = add_object(
            (
                f"<< /Type /Page /Parent {pages_obj_placeholder} 0 R "
                f"/MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
                f"/Contents {content_obj} 0 R >>"
            ).encode("latin-1")
        )
        page_object_numbers.append(page_obj)
    kids = " ".join(f"{page_number} 0 R" for page_number in page_object_numbers)
    objects[pages_obj_placeholder - 1] = (
        f"<< /Type /Pages /Count {len(page_object_numbers)} /Kids [{kids}] >>".encode("latin-1")
    )
    catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj_placeholder} 0 R >>".encode("latin-1"))
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("latin-1"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(pdf)


def write_pdf_report(report: VerificationReport, content: str) -> None:
    report.pdf_report_path.parent.mkdir(parents=True, exist_ok=True)
    report.pdf_report_path.write_bytes(build_pdf_bytes(content))


def wp_failure(returncode: int, stdout: str) -> str | None:
    if returncode != 0:
        return f"Frama-C exited with code {returncode}"
    summaries = re.findall(r"Proved goals:\s*(\d+)\s*/\s*(\d+)", stdout)
    if not summaries:
        return "WP did not produce a proved-goals summary"
    proved, total = map(int, summaries[-1])
    if total == 0:
        return "WP generated no proof goals"
    if proved != total:
        return f"WP proved {proved} of {total} goals"
    return None


def run_framac_wp(
    source_path: pathlib.Path,
    frama_c_options: list[str] | None = None,
    verification_json: pathlib.Path | None = None,
) -> int:
    if verification_json:
        verification_json.unlink(missing_ok=True)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    framac = shutil.which("frama-c")
    cmd = [framac or "frama-c", *(frama_c_options or []), "-wp", str(source_path)]
    print(f"Running: {' '.join(cmd)}")
    try:
        if framac is None:
            raise FileNotFoundError("Frama-C was not found in PATH; install Frama-C with WP")
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError as error:
        completed = subprocess.CompletedProcess(cmd, 127, "", str(error))
    failure = wp_failure(completed.returncode, completed.stdout or "")
    if verification_json:
        verification_json.parent.mkdir(parents=True, exist_ok=True)
        verification_json.write_text(json.dumps({
            "schema_version": 1, "command": cmd, "returncode": completed.returncode,
            "source_sha256": source_sha256,
            "stdout": completed.stdout or "", "stderr": completed.stderr or "",
            "verified": failure is None, "verification_error": failure,
        }, indent=2) + "\n", encoding="utf-8")
    raw_output = (completed.stdout or "") + (completed.stderr or "")
    if raw_output:
        print(raw_output, end="" if raw_output.endswith("\n") else "\n")
    report = build_verification_report(cmd, source_path, completed.returncode, raw_output, failure)
    full_report = format_full_report(report)
    write_text_report(report, full_report)
    write_pdf_report(report, full_report)
    print(format_terminal_report(report))
    if failure is None:
        print("Frama-C WP verification completed successfully.")
    else:
        print(f"Frama-C WP verification failed: {failure}.", file=sys.stderr)
    return completed.returncode or (1 if failure else 0)
