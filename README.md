# LOGOS: LLM-Based Generation of Function Contracts for C

LOGOS provides a skill for authoring ACSL function contracts and a Python wrapper
that inserts those contracts into C source and optionally verifies the result
with Frama-C WP. The agent decides contract semantics; the wrapper handles
rendering, annotation, verification, and reports.

The input must already contain ACSL. Input programs, case studies, generated
contracts, annotated source, and proof reports belong in external project
directories and are not distributed in this repository.

## Choose a Workflow

| Workflow | How it runs | Guide |
|---|---|---|
| Standalone LOGOS | Ask Codex to author contracts, then apply and optionally verify them with the local wrapper | [Standalone usage](docs/USAGE.md) |
| AutoDeduct with local tools | Host Codex generates JSON; AutoDeduct runs the wrapper and Frama-C locally | [AutoDeduct integration](docs/AUTODEDUCT.md) |
| AutoDeduct with Docker verification | Host Codex generates JSON; AutoDeduct runs the wrapper and Frama-C in Docker | [AutoDeduct integration](docs/AUTODEDUCT.md) |

AutoDeduct's LLM workflow runs Codex on the host. Running Codex inside its
container is unsupported. Docker is optional when verification dependencies are
installed locally.

## Documentation

- [Setup](docs/SETUP.md): Python, libclang, verification tools, and platform support.
- [Standalone usage](docs/USAGE.md): agent prompts, contract files, and wrapper commands.
- [AutoDeduct integration](docs/AUTODEDUCT.md): host launcher, local/Docker runtimes, and the JSON handoff.
- [Verification and scope](docs/VERIFICATION.md): proof results, reports, limitations, and artifact policy.
- [Skill instructions](skill/SKILL.md): instructions and contract schema used by the agent.

## Repository Layout

- `skill/SKILL.md`: contract-generation skill.
- `skill/scripts/generate_acsl.py`: Python wrapper entry point.
- `skill/scripts/acsl_tool/`: parsing, rendering, annotation, and verification.
- `tests/`: automated checks.
- `scripts/measure_codex_contracts.py`: measurement utility.
- `docs/`: user guides.

## License

LOGOS's original software is licensed under the **GNU General Public License
v2.0 only** (`GPL-2.0-only`). See [LICENSE](LICENSE) for the full terms and
[NOTICE](NOTICE) for licensing scope and separately owned material.
