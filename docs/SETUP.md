# Setup

[Documentation index](../README.md#documentation)

Choose [standalone usage](USAGE.md) or [AutoDeduct integration](AUTODEDUCT.md)
before installing dependencies. AutoDeduct's Docker runtime supplies the wrapper
dependencies in its verifier image; the host still needs Python, authenticated
Codex CLI, AutoDeduct, and Docker. The launcher extracts the skill from the
prepared verifier image for the host agent. A local LOGOS checkout is required
for standalone use and AutoDeduct's local runtime; it is unnecessary when
running AutoDeduct with an already prepared Docker image.

## Standalone and Local Verification Requirements

- Python 3.10 or newer.
- The libclang shared library, loadable by Python, for C parsing.
- Codex or manually authored contract JSON for undocumented functions. The
  wrapper does not infer contract semantics.
- Frama-C with the WP plugin and configured provers when verification is requested.

LOGOS loads libclang directly with `ctypes`. The `clang` executable alone is
insufficient; the Python `clang` package is unnecessary.

## Install libclang

| Platform | Installation |
|---|---|
| macOS | `xcode-select --install` for Apple Command Line Tools, or `brew install llvm` |
| Debian/Ubuntu | `sudo apt install libclang-dev` |
| Windows x64 | `winget install --id LLVM.LLVM --exact`, or the [official LLVM installer](https://github.com/llvm/llvm-project/releases) |

On Windows, use x64 Python with x64 LLVM and confirm that
`C:\Program Files\LLVM\bin\libclang.dll` exists.

LOGOS searches standard Apple Command Line Tools, Xcode, and Homebrew LLVM
locations on macOS, and shared-library locations on Linux. On Windows it checks
`%ProgramFiles%\LLVM\bin\libclang.dll` and Python's library discovery.

For a custom installation or a discovery failure, set `LIBCLANG_FILE` to the
compatible shared library before starting a new LOGOS process:

```bash
# Homebrew LLVM on macOS:
export LIBCLANG_FILE="$(brew --prefix llvm)/lib/libclang.dylib"

# Linux: adjust this path to your installed version.
# export LIBCLANG_FILE=/usr/lib/llvm-19/lib/libclang.so
```

PowerShell:

```powershell
$env:LIBCLANG_FILE = 'C:\Program Files\LLVM\bin\libclang.dll'
```

`LIBCLANG_FILE` overrides automatic discovery. Its library must match the
architecture of the Python process. A missing or unloadable library is an
installation error; LOGOS stops before writing output instead of falling back
to partial function detection.

## Verification Tools

Install Frama-C with WP and configure suitable provers, such as Alt-Ergo, using
the instructions for your Frama-C distribution. The wrapper resolves `frama-c`
from `PATH`. Check the executable before requesting verification:

```bash
frama-c -version
frama-c -wp-help
```

The default wrapper command is `frama-c -wp <annotated-file>`. Additional
verification options can be forwarded as described in
[Verification and scope](VERIFICATION.md#verification-options).

## Check the Installation

From the LOGOS checkout:

```bash
python3 skill/scripts/generate_acsl.py --help
python3 -m unittest discover -s tests -v
```

On Windows, use `python` if `python3` is unavailable. The tests check parsing,
contract rendering, annotation, and verification-report handling. They do not
replace a proof run against your program.

Before verification, check its runtime dependencies:

```bash
python3 skill/scripts/generate_acsl.py --check-dependencies
```

This checks libclang and the `frama-c` executable without reading a source file
or calling a model. Annotation-only use does not require Frama-C or this
verification preflight. AutoDeduct uses it before generation because both LLM
runtimes also verify. It does not establish that the prover setup can complete
a proof.

## Platform Coverage

The native Windows x64 workflow runs the Python suite with automatic libclang
discovery and an explicit DLL path. Tests include CRLF input, paths with spaces,
and missing-library errors.

Native Windows Frama-C verification, Windows ARM64, and 32-bit installations are
not validated. Use WSL for AutoDeduct's Docker verification runtime. Full local
AutoDeduct verification has not been validated end to end on every platform.

## Skill Access

An agent must actually read [SKILL.md](../skill/SKILL.md) to follow its workflow;
having the repository on disk alone does not activate it. You can install the
skill in your agent's skill directory or give the agent its full path explicitly.
AutoDeduct supplies that path through `--llm-skill` or `AUTODEDUCT_LLM_SKILL`, so
global skill installation is unnecessary for its local runtime. Its Docker
runtime extracts `/opt/logos/skill/SKILL.md` from the selected image into a
temporary host cache and uses the same pinned image for verification.
`--llm-skill` and a separate local LOGOS checkout are unnecessary for Docker
execution. AutoDeduct's standard Dockerfile fetches and includes LOGOS by
default, so building that image also needs no host LOGOS checkout; see
[AutoDeduct integration](AUTODEDUCT.md).
