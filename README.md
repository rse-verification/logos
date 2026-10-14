# LOGOS: LLM-Based Generation of Function Contracts for C

This repository provides a Codex skill and a small Python wrapper for extending ACSL annotations in C source files.

Input programs, case studies, and generated contracts are supplied from external project directories. They are not distributed in this repository.

## License

LOGOS's original software is licensed under the **GNU General Public License v2.0 only** (`GPL-2.0-only`). See [LICENSE](LICENSE) for the full terms and [NOTICE](NOTICE) for licensing scope and separately owned material.


## Recommended Usage

The easiest way to use this project is to ask Codex to run the full workflow for you with one prompt.

Recommended prompt:

```text
Use the acsl-contract-generator skill on input/<file>. Read the existing ACSL style, decide the ACSL contracts for the undocumented functions, save them in contracts/<file>.contracts.json, run the Python wrapper to apply them into results/<file>.annotated.c, and then ask me whether to verify the result with frama-c -wp and generate the report files.
```

What this prompt tells Codex to do:

1. Read the source file in `input/`.
2. Decide what the ACSL contracts should say.
3. Save those contracts in a JSON file.
4. Run the Python wrapper to insert them deterministically.
5. Ask whether to run `frama-c -wp`.
6. If verification is approved, generate the text and PDF reports.

The end user does not need to choose between a Python path and an LLM path if they use the prompt above. Codex handles the contract reasoning, and the Python wrapper handles deterministic source rewriting and verification.

## Manual Workflow

If you want to run the steps yourself, the intended workflow is:

1. Select a C source file in an external project directory.
2. Make sure the source already contains some ACSL, such as `/*@` or `//@`.
3. Write the contracts you want to insert in a JSON file.
4. Run the wrapper to insert those contracts deterministically.
5. Save the generated output into `results/`.
6. Optionally verify the generated result with Frama-C WP.

## Repository Layout

- Input C files: supplied from an external project directory.
- `results/main.annotated.c`: Generated output file with additional ACSL.
- `contracts/`: Optional home for structured contract specifications.
- `skill/SKILL.md`: Skill instructions for Codex.
- `skill/scripts/generate_acsl.py`: Python wrapper that performs the generation.

## Requirements

- `python3`
- The **libclang shared library**, loadable by Python, is required for C parsing. Having the `clang` executable in `PATH` alone is not sufficient.
- Optional: `frama-c` with the WP plugin available in `PATH`

Install libclang if it is missing:

- **macOS:** `xcode-select --install` (Apple Command Line Tools), or `brew install llvm`.
- **Debian/Ubuntu:** `sudo apt install libclang-dev`.
- **Windows (x64):** install LLVM with `winget install --id LLVM.LLVM --exact`, or use the [official LLVM release installer](https://github.com/llvm/llvm-project/releases). Use x64 Python with x64 LLVM and confirm that `C:\Program Files\LLVM\bin\libclang.dll` exists.

LOGOS discovers the standard Apple Command Line Tools, Xcode, and Homebrew LLVM locations on macOS, and shared-library locations on Linux. For a custom installation, or if discovery fails, point to the library explicitly before running LOGOS:

```bash
# Homebrew LLVM (macOS):
export LIBCLANG_FILE="$(brew --prefix llvm)/lib/libclang.dylib"
# Linux example (adjust the version/path to your installation):
# export LIBCLANG_FILE=/usr/lib/llvm-19/lib/libclang.so
```

On Windows, LOGOS checks `%ProgramFiles%\LLVM\bin\libclang.dll` and searches `PATH` through Python's library discovery. For a custom LLVM location, set the DLL path in PowerShell:

```powershell
$env:LIBCLANG_FILE = 'C:\Program Files\LLVM\bin\libclang.dll'
python -m unittest discover -s tests -v
```

`LIBCLANG_FILE` takes precedence over automatic discovery. The library must match the architecture of the Python process. Python bindings from the `clang` pip package are not needed; LOGOS loads the shared library directly with `ctypes`.

If libclang cannot be loaded, LOGOS exits with an installation/configuration error before writing output. It does not silently fall back to partial function detection.

Check your setup and run the tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The Windows compatibility workflow runs the full suite with automatic discovery and an explicit DLL path on a native Windows x64 runner, then generates all five benchmark annotations. Tests also cover CRLF input, paths with spaces, and missing-library errors. This checks the Python/ACSL generation workflow; Frama-C WP and the Bash benchmark scripts are outside the native Windows test coverage. Windows ARM64 and 32-bit installations are not covered.

## Command Line Usage

This section is the manual fallback. If you are using Codex with the recommended prompt, you usually do not need to run these commands yourself.

Apply explicitly authored contracts from JSON:

```bash
python3 skill/scripts/generate_acsl.py input/main.c -o results/main.annotated.c --contracts contracts/main.contracts.json
```

The `--contracts` file supports both legacy raw ACSL strings and a structured V2 schema. In the V2 schema, Python renders the ACSL block deterministically instead of pasting only free-form strings.

Example V2 contract spec:

Provide a structured JSON contract using the fields described in this skill; use names and clauses from your external input program.

The `--contracts` file is required for undocumented functions. The wrapper does not invent missing contract semantics locally.

Overwrite the input file:

```bash
python3 skill/scripts/generate_acsl.py input/main.c --in-place
```

Generate ACSL and immediately run Frama-C WP:

```bash
python3 skill/scripts/generate_acsl.py input/main.c -o results/main.annotated.c --verify
```

This verification run prints a readable summary in the terminal and saves:

- `results/main.annotated.wp-report.txt`
- `results/main.annotated.wp-report.pdf`

Generate ACSL without showing the verification question:

```bash
python3 skill/scripts/generate_acsl.py input/main.c -o results/main.annotated.c --no-verify-prompt
```

Show how the tool handled each function:

```bash
python3 skill/scripts/generate_acsl.py input/main.c -o results/main.annotated.c --contracts contracts/main.contracts.json --explain
```

## AutoDeduct Integration

LOGOS implements the skill interface used by AutoDeduct's [`llm-skill-mode` branch](https://github.com/rse-verification/auto-deduct/tree/llm-skill-mode). Point `AUTODEDUCT_LLM_SKILL` at the absolute path of `skill/SKILL.md`; global skill installation is unnecessary when AutoDeduct supplies this path.

AutoDeduct is the host launcher. It runs authenticated Codex locally with a
`workflow: "generate-only"` task; Codex writes contract JSON and stops.
AutoDeduct then invokes this repository's Python wrapper, checks the resulting
source and proof evidence, and writes its final report. The model does not
launch verification or write the verification report.

```shell
# Host Python, Codex, libclang, Frama-C/WP and provers installed locally:
autodeduct llm --llm-runtime local \
  --llm-skill /absolute/path/to/logos/skill/SKILL.md path/to/program.c

# Host Python and authenticated Codex; LOGOS wrapper and tools in Docker:
autodeduct llm --llm-runtime docker \
  --llm-skill /absolute/path/to/logos/skill/SKILL.md path/to/program.c
```

Docker is optional. With Docker, build AutoDeduct's `auto-deduct:logos` image
from this checkout, then invoke the launcher on the host. The container includes
Python, libclang, the LOGOS wrapper, Frama-C/WP and provers. It contains no Codex
installation or login credentials. Inputs/headers are mounted read-only, outputs
are writable, and the verifier container has no network access. Host libclang or
Frama-C installations are unnecessary for this runtime. Running Codex inside a
container is unsupported by this integration. Docker mode supports Linux/macOS
and Windows through WSL; native Windows Frama-C verification is not validated.
See AutoDeduct's [setup instructions](https://github.com/rse-verification/auto-deduct/blob/llm-skill-mode/docs/INSTALLATION.md#logos-for-llm-mode).

Standalone LOGOS usage still requires local Python and libclang, and local
Frama-C/WP with provers when verification is requested. Older AutoDeduct tasks
without the generation-only marker retain the skill's full workflow.

The wrapper accepts repeated `--frama-c-option=VALUE` arguments and writes process evidence with `--verification-json FILE` (requires `--verify`):

```bash
python3 skill/scripts/generate_acsl.py /work/input.c \
  --contracts /work/proof/contracts.json -o /work/proof/inferred.c \
  --verify --verification-json /work/proof/verification.json \
  --frama-c-option=-main --frama-c-option=main \
  --frama-c-option=-wp-rte
```

Evidence includes `schema_version: 1`, the exact command and process return code, captured stdout/stderr, and the SHA-256 of the annotated source bytes. Only the wrapper writes this evidence. Frama-C options are forwarded to verification; they do not configure libclang's annotation parser.

**Verification succeeds only when Frama-C exits zero and its last proved-goals summary contains a nonzero total with every goal proved.** Missing, zero, or incomplete goals make the wrapper exit nonzero and mark its text/PDF reports as failed. The JSON `returncode` preserves the actual process status; `verified` records the proof outcome, so `returncode: 0` alone does not mean a successful proof.

AutoDeduct validates the evidence and annotation-only source changes. LLM mode does not run Saida/TriCera, ISP/Eva, or the ISP reachable-helper check. LOGOS generates function contracts; loop invariants and project-specific parser flags remain limitations.

## Interactive Behavior

In an interactive terminal session, after generating the annotated file, the wrapper asks:

```text
Do you want to verify it with `frama-c -wp` and save a PDF report? [y/N]
```

If the answer is `y` or `yes`, it runs:

```bash
frama-c -wp <generated-file>
```

Then it:

- prints a clear verification summary in the terminal
- saves a text report in `results/`
- saves a PDF report in `results/`

## What The Wrapper Does

- Detects whether the input already contains ACSL.
- Preserves existing ACSL blocks.
- Requires Codex-authored contracts for undocumented functions.
- Accepts explicit contracts from a JSON file through `--contracts`.
- Renders structured V2 contract specs into ACSL deterministically.
- Validates contract metadata and warns when a contracts file does not match the current source file.
- Cleans obvious pasted shell prompt noise at the end of the source file.
- Repairs a missing trailing closing brace when the source was truncated by pasted shell output.
- When verification runs, generates `.wp-report.txt` and `.wp-report.pdf` report files.

## Supported Scope

The parser requires `libclang` (see Requirements above). The intended workflow is reliable when:

- the file already contains ACSL somewhere in the source
- the source can be parsed by the local Clang installation
- contracts for undocumented functions are provided explicitly through `--contracts`

Known unsupported or risky patterns remain:

- files that require project-specific compile flags, include paths, or macro definitions that are not provided to the parser
- heavy preprocessor rewriting around top-level function declarations
- contract generation without a Codex-authored contracts file

These limitations are currently an explicit product boundary. If the tool needs full project-aware parsing, the next step is to thread compile flags and include paths into the Clang-based parser.

## Contract Metadata

Structured contract files can include metadata for release-grade validation:

- `metadata.source`: expected source file path
- `metadata.source_sha256`: SHA-256 of the source file used when the contracts were authored

If the current source file does not match the metadata, the tool prints a warning that the contracts may be stale.

## V2 Direction

The cleaner V2 workflow treats the source file in `input/` as the canonical human-edited artifact and treats files in `results/` as generated output. The preferred contract handoff is a structured JSON specification instead of raw ACSL strings, with Python responsible for rendering ACSL formatting consistently.

## Artifact Policy

The recommended artifact ownership is:

- `input/`: canonical source files edited by humans
- `contracts/`: reviewed contract specifications authored by Codex or humans
- `results/`: generated outputs that can be regenerated at any time

Keep input programs and generated contracts in your external project. Treat `results/` as build-style output unless your process explicitly requires checked-in generated annotations or proof reports.

## Codex-First Workflow

Typical flow:

1. Ask Codex to inspect the source file and decide the ACSL contracts.
2. Let Codex save those contracts in a JSON file.
3. Run the Python wrapper with `--contracts <file.json>` to insert them.
4. Verify the refined output with `frama-c -wp`.

## How To Ask Codex To Use It

Use a direct prompt that names the task clearly. These are good prompts:

```text
Use the acsl-contract-generator skill on input/main.c. Read the existing ACSL style, decide the ACSL contracts for the undocumented functions, save them to contracts/main.contracts.json, run the Python wrapper to insert them into results/main.annotated.c, and then ask me whether to verify it with frama-c -wp and generate the report files.
```

```text
Use acsl-contract-generator on input/main.c. Generate the contracts semantically, write them to a contracts JSON file, apply them with the Python wrapper, and then offer frama-c -wp verification with reports.
```

## Recommended Prompt Template

Replace the file names as needed:

```text
Use the acsl-contract-generator skill on input/<file>. Read the source code, detect the existing ACSL style, decide the ACSL contracts for the other functions in the source code, save them to contracts/<file>.contracts.json, run the Python wrapper to apply them into results/<file>.annotated.c, and then ask me if I want to verify it with frama-c -wp and save a PDF report.
```

Shorter prompt:

```text
Use acsl-contract-generator on input/<file>. Run the full Codex-plus-wrapper workflow: decide contracts, write a contracts JSON file, apply it with the Python wrapper, and offer frama-c -wp verification with reports.
```

## Notes

- The wrapper expects ACSL to already exist in the file. It does not invent a project-wide style from scratch.
- Undocumented functions need explicit Codex-authored contracts passed through `--contracts`.
- Verification with Frama-C WP remains the final filter.
- If the user wants the whole workflow handled by Codex, the prompt should explicitly mention deciding contracts, writing the contracts JSON file, applying it with the wrapper, and verification.

## Tests

Run the current automated checks with:

```bash
python3 -m unittest discover -s tests
```
