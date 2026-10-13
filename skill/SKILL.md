---
name: acsl-contract-generator
license: GPL-2.0-only
description: Generate structured ACSL contracts for undocumented functions in a C file that already contains ACSL, then apply them with the local Python wrapper and optionally verify the result.
---
# ACSL Contract Generator

Use this skill when:
- the input is a C file
- the file already contains at least one ACSL marker such as `/*@` or `//@`
- Codex should decide contract semantics
- Python should apply contracts deterministically

## Prerequisites

- Python 3 and the libclang shared library are required. The `clang` executable alone is insufficient; Python loads libclang directly without additional Python bindings.
- macOS: install Apple Command Line Tools with `xcode-select --install`, or LLVM with `brew install llvm`. Standard Apple and Homebrew library paths are detected automatically.
- Debian/Ubuntu: install `libclang-dev` with `sudo apt install libclang-dev`.
- Windows x64: install LLVM with `winget install --id LLVM.LLVM --exact` and use x64 Python. LOGOS checks `%ProgramFiles%\LLVM\bin\libclang.dll` and library discovery through `PATH`. For a custom path in PowerShell: `$env:LIBCLANG_FILE = 'C:\Program Files\LLVM\bin\libclang.dll'`. Run Python commands with `python` if `python3` is unavailable.
- For a custom installation, set `LIBCLANG_FILE` to the full path of the compatible `libclang.dylib`, `libclang.so`, or `libclang.dll`. This overrides automatic discovery.
- Native Windows CI covers Python/ACSL generation; it does not validate Frama-C WP or Bash scripts on Windows.
- If loading fails, stop and resolve the dependency/configuration error. Do not treat it as a failed proof or generate output using partial function detection.
- Frama-C with WP in `PATH` is additionally required only when verification is requested.

## Default Flow

1. Read the source file and confirm it already contains ACSL.
2. Read the existing ACSL style and use Codex to author contracts for undocumented functions.
3. Write those Codex-authored contracts as structured JSON in the schema below.
4. Write structured contracts to `contracts/<stem>.contracts.json`.
5. Run:
   ```bash
   python3 skill/scripts/generate_acsl.py input/<file>.c -o results/<stem>.annotated.c --contracts contracts/<stem>.contracts.json
   ```
6. Ask before verification unless the user explicitly requested verification.

## AutoDeduct Integration

When AutoDeduct supplies `llm-task.json`, read its absolute artifact paths and use them instead of the default `contracts/` and `results/` paths. Invoke `scripts/generate_acsl.py` relative to this SKILL.md's directory, even when the working directory is the task output directory.

- Include `metadata.source_sha256` computed from the UTF-8 source text read by Python (`Path(source).read_text(encoding="utf-8").encode("utf-8")`).
- Author structured function contracts, then run the wrapper with the task's `source`, `--contracts`, `-o`, `--verify`, and `--verification-json` paths.
- Forward **each** item of `verification_options` as a separate `--frama-c-option=VALUE`, in order (including option values such as the entry function name).
- Verification is already authorized by the task. Only the wrapper writes verification JSON; never fabricate or edit it.
- Preserve input source and existing contracts. AutoDeduct accepts only ACSL block insertions and rejects source repair or other rewrites.
- A successful proof requires a nonzero goal count and every goal proved. Missing, zero, or incomplete summaries are failures even if Frama-C exits zero.

## Authoring Strategy

- Codex is responsible for contract semantics.
- The Python tool validates, inserts, and verifies contracts; it does not infer missing contract meaning.
- Reuse existing documented ACSL style in the same file when authoring new contracts, but write the final decision explicitly into the structured JSON.
## Contract Schema

Write contract files in this shape:

```json
{
  "format": "acsl-contracts-v2",
  "metadata": {
    "source": "input/<file>.c",
    "source_sha256": "<sha256>"
  },
  "contracts": {
    "<function_name>": {
      "requires": ["..."],
      "assigns": ["..."],
      "ensures": ["..."]
    }
  }
}
```
Allowed per-function fields:
- `comments`
- `requires`
- `decreases`
- `assigns`
- `ensures`
- `behaviors`
- `complete_behaviors`
- `disjoint_behaviors`
- `raw`

Prefer the smallest useful subset:
- usually only `assigns`, `requires`, and `ensures`
- use advanced fields only when needed

## Canonical Example

Provide a structured JSON contract using the fields described in this skill; use names and clauses from your external input program.

## Output Paths

- contracts: `contracts/<stem>.contracts.json`
- ACSL output: `results/<stem>.annotated.c`
- Frama-C reports: `results/<stem>.annotated.wp-report.txt` and `.pdf`

## Verification Rules

- Generate `results/<stem>.annotated.c`.
- Ask whether to run `frama-c -wp` unless the user already asked for verification.

## Important Constraints

- If the source has no ACSL, stop and say the file is outside the supported workflow.
- If a function has no ACSL and no provided contract entry, stop and ask Codex to author one instead of inventing it in Python.
- Do not invent raw ACSL formatting in the JSON; write structured schema fields.
- Treat `input/` as canonical input and `results/` as generated output.
- Prefer the skill and this schema as the runtime source of truth; do not rely on README unless necessary.
- If an existing function contract is available, prefer preserving and reusing its contract structure before inventing unrelated clauses.

## Minimal Prompt Template

```text
Use the acsl-contract-generator skill on input/<file>. Read the existing ACSL style, generate structured contracts for undocumented functions, save them to contracts/<stem>.contracts.json, apply them into results/<stem>.annotated.c, and then ask whether to verify.
```
