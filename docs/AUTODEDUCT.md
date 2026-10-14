# AutoDeduct Integration

[Documentation index](../README.md#documentation)

LOGOS supplies the contract-generation skill and verification wrapper used by
AutoDeduct's [`llm-skill-mode` branch](https://github.com/rse-verification/auto-deduct/tree/llm-skill-mode).
The compatible LOGOS changes are on `main`.

Follow AutoDeduct's [LLM setup and usage guide](https://github.com/rse-verification/auto-deduct/blob/llm-skill-mode/docs/LLM.md)
for host installation, the supported LOGOS revision, and Docker image builds.
Its [usage index](https://github.com/rse-verification/auto-deduct/blob/llm-skill-mode/docs/USAGE.md)
separates LLM and deductive commands; its
[installation guide](https://github.com/rse-verification/auto-deduct/blob/llm-skill-mode/docs/INSTALLATION.md)
covers the traditional toolchain.

## Choose Where Verification Runs

| Requirement | `--llm-runtime local` | `--llm-runtime docker` |
|---|---|---|
| Host Python and AutoDeduct launcher | Required | Required |
| Host Codex CLI and login | Required | Required |
| Local LOGOS checkout and skill path | Required | Skill extracted from verifier image |
| Wrapper, libclang, Frama-C/WP, and provers | Installed on host | Packaged in verifier image |
| Docker | Unnecessary | Required |

Both modes start from your host terminal. `local` is the default. Docker runs
only when selected explicitly.

The host needs the AutoDeduct executable available through `PATH` to use the
name `autodeduct`. A separate package installation is unnecessary: clone the
repository and use `./bin/autodeduct`, or add its `bin/` directory to `PATH`.

From the AutoDeduct checkout, after configuring the chosen runtime:

```bash
./bin/autodeduct llm --llm-runtime local \
  --llm-skill /absolute/path/to/logos/skill/SKILL.md \
  --output-dir /project/results/autodeduct /project/input/program.c
```

For Docker verification:

```bash
./bin/autodeduct llm --llm-runtime docker \
  --output-dir /project/results/autodeduct /project/input/program.c
```

For local verification, you can set `AUTODEDUCT_LLM_SKILL` to the absolute skill
path instead of repeating `--llm-skill`. Global skill installation is unnecessary.

Docker verification uses the skill packaged at `/opt/logos/skill/SKILL.md` in
the prepared image. AutoDeduct resolves the image to an immutable image ID,
extracts its skill into a temporary host cache, and gives that path to Codex.
The wrapper runs from the same image ID. Users of a prepared image need no
local LOGOS checkout or `--llm-skill` flag.

The standard `auto-deduct:latest` image includes LOGOS alongside Saida, ISP
and TriCera. Its Dockerfile fetches a pinned LOGOS revision during the build;
no separate host LOGOS checkout or extra image layer is needed. Run the standard
image build from the AutoDeduct checkout on your host. Follow
[AutoDeduct's image build instructions](https://github.com/rse-verification/auto-deduct/blob/llm-skill-mode/docs/LLM.md#build-the-verifier-image).

## Why the Launcher Runs on the Host

The launcher coordinates host Codex and the verification tools. Codex uses the
host's existing login and sandbox. In Docker mode, AutoDeduct mounts the input
and headers read-only, mounts outputs writable, and runs the wrapper in the
verifier container. The agent does not need Docker access.

Running Codex inside the AutoDeduct container is unsupported and rejected by
the LLM launcher. Earlier attempts encountered nested sandbox restrictions and
introduced container authentication setup. The supported verifier image has no
Codex installation or model credentials and runs without network access.

Docker mode supports Linux/macOS and Windows through WSL. Native Windows
Frama-C verification is not validated. The extracted skill and wrapper come
from the same pinned image; use a compatible image from AutoDeduct's setup guide.

## The Contract and Report Handoff

1. AutoDeduct selects the local skill or extracts the Docker image's skill,
   checks verification dependencies, and writes `llm-task.json` with
   source/output paths, verification options, and `workflow: "generate-only"`.
2. Host Codex reads the selected LOGOS skill and source, then writes
   `llm-contracts.json`, including the source hash. It stops after generation.
3. AutoDeduct checks that handoff, then explicitly invokes
   `skill/scripts/generate_acsl.py` with the contracts, annotated output path,
   `--verify`, `--verification-json`, and requested Frama-C options.
4. The wrapper annotates the source, runs Frama-C WP, and writes verification
   JSON plus text/PDF reports.
5. AutoDeduct reads the wrapper's JSON evidence, checks source changes and
   proof results, and writes its final `report.json`.

The LLM writes contract JSON. The wrapper writes verification evidence. The
text/PDF reports support human review; AutoDeduct consumes the JSON evidence.
Generating contract JSON alone is insufficient for a successful verification.

Docker runs retain an `llm-skill.md` snapshot for review. The recorded image ID
and skill hash identify the packaged instructions and verifier used for that run.

Standalone LOGOS and older tasks without the generation-only marker retain the
skill's complete generation, annotation, and optional verification workflow.

## Scope of This Mode

The current AutoDeduct runner uses Codex-specific CLI arguments. Changing
`--llm-runner` to an arbitrary LLM executable is insufficient to support another
provider; it needs an adapter that produces the same contract handoff.

LLM mode does not run Saida/TriCera, ISP/Eva, or the traditional ISP
reachable-helper check. See [verification and scope](VERIFICATION.md) for LOGOS
limitations and proof interpretation.
