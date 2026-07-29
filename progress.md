# ShellPa Progress

## Current release

- Version: `0.2.0`
- Status: tested release checkpoint
- Repository: private
- Supported Python: 3.10 and newer
- Supported systems: Windows, Linux, and macOS
- Public PyPI distribution: deferred until after v0.3

## Product direction

ShellPa translates natural-language intent into a native command for the
current operating system and shell. The AI proposes a command, ShellPa applies
a deterministic local safety policy, and the user remains the final authority.

The stable processing path is:

```text
User intent
    -> structured command proposal
    -> deterministic safety assessment
    -> permission decision
    -> observable execution
    -> structured result
    -> redacted recovery when needed
```

## Completed in v0.2

### Domain and configuration foundation

- Added validated models for proposals, risk assessments, permission decisions,
  execution requests/results, and recovery context.
- Added provider-aware configuration validation.
- Supported project-local `.env` and user-level `~/.shellpa.env`
  configuration.
- Kept credentials and private planning files outside version control.

### Deterministic safety

- Added read-only, normal, high-risk, critical, and unknown classifications.
- Added protected-path and destructive-operation rules across PowerShell, CMD,
  Bash, and Zsh.
- Added Ask, Plan, and Trusted permission modes.
- Added typed confirmation for high-risk operations.
- Kept critical operations manual-only.
- Prevented `--force` and recovery attempts from bypassing safety policy.

### Execution engine

- Added streaming stdout and stderr.
- Added bounded diagnostic capture.
- Added cancellation, timeout, and passthrough support.
- Distinguished failures, cancellation, and timeouts.
- Added partial-effect warnings and fresh safety assessment for recovery
  commands.

### Interactive experience

- Added a `prompt_toolkit` interactive session with history, completion,
  keyboard navigation, and a status footer.
- Added themes, live theme preview, reduced-motion behavior, startup identity,
  activity animation, mode identities, and first-run guidance.
- Added interactive `/help`, `/mode`, `/model`, `/config`, `/theme`, `/motion`,
  `/doctor`, `/about`, `/clear`, `/history`, and `/exit` commands.
- Added a persistent About hub with developer and repository links.

### Commands and diagnostics

- Added first-class `run`, `config`, `doctor`, `about`, `help`, and `version`
  commands.
- Preserved the shorter `shellpa "<request>"` interface.
- Added offline installation diagnostics and optional provider-host
  reachability checks.
- Added privacy-safe local JSONL event logging with `SHELLPA_LOGGING=0` opt-out.
- Prevented default doctor diagnostics from importing the model provider or
  attempting network access.

### Release quality

- Added automated formatting and linting with Ruff.
- Added static type checking with mypy.
- Added Windows, Linux, and macOS GitHub Actions validation.
- Added package build verification and public v0.2 migration documentation.
- Passed 171 automated tests and real-terminal acceptance testing.

## Current quality status

- Ruff formatting: passing
- Ruff linting: passing
- Mypy: passing across 17 source modules
- Pytest: 171 tests passing
- Dependency check: passing
- Wheel and source distribution builds: passing
- Secret and private-file package inspection: passing
- Manual Windows terminal test: passing

## Next release: v0.3

The recommended v0.3 focus is workspace awareness:

- detect Git repository state, branch, and modified files;
- identify Python, Node.js, Docker, and other project types;
- identify available project tooling and package managers;
- establish an explicit workspace boundary;
- build a structured, privacy-conscious `WorkspaceContext`;
- show the user which workspace facts influence a generated command;
- test detection across Windows, Linux, and macOS.

The first implementation should be read-only. Conversational memory,
multi-step planning, script generation, checkpoints, and plugins should build
on top of the workspace context rather than precede it.

## Distribution plan

ShellPa remains private during v0.2 and v0.3 development. After v0.3 is
finished and accepted:

1. review the public repository content and license;
2. reserve and verify the package name;
3. publish a release candidate to TestPyPI;
4. test installation in clean Windows, Linux, and macOS environments;
5. make the GitHub repository public if approved;
6. publish the stable package to PyPI.
