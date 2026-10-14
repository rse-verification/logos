# Verification and Scope

[Documentation index](../README.md#documentation)

## Reports and Success Criteria

For `program.annotated.c`, a verification run produces:

- `program.annotated.wp-report.txt`: summary and captured Frama-C output.
- `program.annotated.wp-report.pdf`: a printable version of the text report.
- Optional verification JSON, selected with `--verification-json FILE`.

Verification succeeds only when Frama-C exits zero and the last proved-goals
summary contains a nonzero total with every goal proved. Missing, zero, or
incomplete goals make LOGOS exit nonzero and mark the reports as failed.
A timeout means a goal remains unproved; it does not establish a counterexample.

Verification JSON includes `schema_version: 1`, the exact command, actual
process `returncode`, captured `stdout`/`stderr`, the annotated source's SHA-256,
and `verified`/`verification_error`. A Frama-C `returncode` of zero can coexist
with `verified: false` when the proof is incomplete. The JSON path must be
separate from the source, contracts, annotated output, and human report paths.

The wrapper writes evidence from its process invocation. AutoDeduct additionally
checks the source hash, requested options, and annotation-only changes before
accepting that evidence. These reports are process evidence, not independently
checkable proof certificates.

Proof results depend on the selected entry point, WP memory model, external
function specifications, assumptions, and any admitted statements in the input.
Review those alongside the goal count; a complete count does not validate the
intended requirements or the accuracy of supplied assumptions.

## Verification Options

The wrapper invokes `frama-c -wp` by default. Forward additional arguments with
repeated `--frama-c-option=VALUE` options, including separate option values:

```bash
python3 /absolute/path/to/logos/skill/scripts/generate_acsl.py \
  /project/input/program.c \
  --contracts /project/contracts/program.contracts.json \
  -o /project/results/program.annotated.c \
  --verify --verification-json /project/results/verification.json \
  --frama-c-option=-main --frama-c-option=main \
  --frama-c-option=-wp-rte
```

These options affect Frama-C verification. They do not configure libclang's
annotation parser. Select the actual program entry point and initialization
context; choosing a periodic routine as `-main` can create obligations against
an inappropriate initial state.

## Source Matching

Contract metadata may include `source` and `source_sha256`. The hash is computed
from Python's UTF-8 source text:

```python
hashlib.sha256(Path(source).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
```

This normalizes line endings through Python's text read. It differs from hashing
the original file bytes when the file uses CRLF. Verification evidence instead
hashes the actual annotated file bytes.

Standalone LOGOS warns on a metadata path/hash mismatch and continues. Treat
that warning as a reason to review or regenerate contracts. AutoDeduct's
generation handoff requires a matching source hash and rejects stale contracts.

## Supported Input and Limitations

LOGOS targets valid C files that already contain ACSL and parse with the available
libclang setup. It preserves detected existing function contracts, including
contracts on prototypes, and inserts explicit contracts for undocumented
function definitions in the input file. It accepts block (`/*@ ... */`) and line
(`//@ ...`) annotation forms.

Known boundaries:

- The wrapper requires contract JSON for undocumented functions; it does not
  infer their meaning itself.
- Project-specific Clang include paths, macros, and compile flags are not
  exposed through the wrapper CLI. Frama-C options do not fill that gap.
- Heavy preprocessing around top-level declarations can affect detection.
- LOGOS generates function contracts; automatic loop-invariant generation is
  outside its current workflow.
- LOGOS has no CBMC contract emitter or verification capability.

LOGOS adds ACSL to the supplied source; it does not repair incomplete programs
or remove pasted shell text. AutoDeduct also requires annotation-only changes
and rejects program-code rewrites. Correct malformed input in the external
project before running the workflow.

## Artifact Policy

Keep canonical input source, case-study material, contracts, generated source,
and reports in the external project that owns them. Suggested project folders
are `input/`, `contracts/`, and `results/`; they are not repository content.

Treat generated annotations and reports as reproducible outputs unless your
project explicitly requires storing reviewed results. Preserve the original
source separately, especially when using `--in-place`.

LOGOS's [GPL-2.0-only license](../LICENSE) applies to its original software.
Separately owned inputs retain their existing rights and notices. The LOGOS
license does not change the licenses of analyzed programs or automatically
apply GPL to generated contracts or reports merely because LOGOS produced them.
See [NOTICE](../NOTICE).
