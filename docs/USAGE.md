# Standalone Usage

[Documentation index](../README.md#documentation) · [Setup](SETUP.md)

Use this workflow when asking an agent to run LOGOS directly. For AutoDeduct's
host launcher and runtime choices, see [AutoDeduct integration](AUTODEDUCT.md).

## Prepare the External Project

Keep input C files, contract JSON, annotated copies, and proof reports in your
own project directory. The names `input/`, `contracts/`, and `results/` below are
suggested folders in that external project; they are not shipped LOGOS content.

The source must already contain at least one ACSL marker (`/*@` or `//@`) and
must be valid C for the supported parser setup. Contracts must be provided for
every detected function definition that lacks an existing function contract.
The wrapper also recognizes existing contracts on prototypes and preserves them.

## Ask Codex to Author Contracts

Give Codex the full path to the skill and use paths from your project:

```text
Read /absolute/path/to/logos/skill/SKILL.md and use it on /project/input/program.c.
Read the existing ACSL style, author structured contracts for undocumented
functions, and save them to /project/contracts/program.contracts.json. Apply
them with the LOGOS wrapper into /project/results/program.annotated.c, then
verify with Frama-C WP and produce the reports.
```

This prompt requests verification. If you only want generation and annotation,
say so; the skill otherwise asks before verification unless it was already
requested. The LLM determines contract meaning. The wrapper requires explicit
contracts and does not generate missing semantics on its own.

## Contract JSON

Prefer the structured `acsl-contracts-v2` schema defined in
[the skill](../skill/SKILL.md#contract-schema). It maps function names to clause
lists such as `requires`, `assigns`, and `ensures`. Additional fields support
behaviors and other ACSL clauses. The wrapper renders those fields into ACSL.

Legacy JSON mappings to raw ACSL strings are accepted by the wrapper, but the
skill authors structured fields. Contracts for unknown functions or functions
that already have ACSL are rejected, as are missing contracts for detected
undocumented functions.

Optional metadata records the intended source path and source hash. See
[source matching](VERIFICATION.md#source-matching) for its exact behavior.

## Apply Contracts Manually

Use an absolute path to the LOGOS wrapper so the working directory can remain
your external project:

```bash
python3 /absolute/path/to/logos/skill/scripts/generate_acsl.py \
  /project/input/program.c \
  --contracts /project/contracts/program.contracts.json \
  -o /project/results/program.annotated.c \
  --no-verify-prompt
```

`--no-verify-prompt` makes this annotation-only command suitable for automation.
Without `-o`, the default output is `results/<input-stem>.annotated.c` relative
to the current working directory. Use `--explain` to print how each detected
function was handled.

To overwrite the input deliberately, replace `-o` with `--in-place`:

```bash
python3 /absolute/path/to/logos/skill/scripts/generate_acsl.py \
  /project/input/program.c \
  --contracts /project/contracts/program.contracts.json \
  --in-place --no-verify-prompt
```

Keep a recoverable copy before using `--in-place`.

## Apply and Verify

```bash
python3 /absolute/path/to/logos/skill/scripts/generate_acsl.py \
  /project/input/program.c \
  --contracts /project/contracts/program.contracts.json \
  -o /project/results/program.annotated.c \
  --verify \
  --verification-json /project/results/verification.json
```

The wrapper writes the annotated source, runs WP, and generates text and PDF
reports. `--verification-json` is optional for standalone use and requires
`--verify`. See [reports and success criteria](VERIFICATION.md#reports-and-success-criteria)
before interpreting a successful process exit.

In an interactive terminal, omitting both `--verify` and `--no-verify-prompt`
causes the wrapper to ask whether to verify after annotation. Noninteractive
commands do not prompt. Use `--verify` explicitly when verification is required.
