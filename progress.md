# ShellPa Progress

## Current release

- Version: `0.3.0`
- Status: owner-accepted private release checkpoint
- Repository: private
- Supported Python: 3.10 and newer
- Supported systems: Windows, Linux, and macOS
- Public PyPI distribution: not published; requires a separate owner-approved
  release process

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

## Completed through v0.2

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

## Completed in v0.3

### Workspace awareness

- Added a typed, read-only `WorkspaceContext`.
- Added deterministic workspace-boundary resolution.
- Added allowlisted project-marker and project-type detection.
- Added known-tool and active Python-environment detection without launching
  detected tools.
- Added bounded Git branch, detached/unborn state, and tracked/untracked change
  counts without retaining filenames.
- Added `shellpa context`, `/context`, and a compact interactive workspace
  identity.
- Kept local paths separate from the smaller provider-safe summary.

### Safe generation integration

- Added the redacted workspace summary to initial command generation and
  recovery.
- Framed workspace metadata as untrusted observations that cannot override user
  intent or ShellPa safety policy.
- Preserved one workspace snapshot throughout an execution/recovery flow.
- Continued to exclude source contents, secret-file contents, and arbitrary
  Git filenames.

### Optional Codex subscription provider

- Added a provider-neutral generation boundary.
- Added the optional pinned `openai-codex` SDK and its embedded runtime.
- Added interactive installation after explicit approval.
- Added browser and device-code ChatGPT authentication without ShellPa reading
  or storing credentials.
- Isolated Codex generation in an ephemeral temporary workspace with read-only
  sandboxing, deny-all approval, disabled tools, strict structured output, and
  a bounded timeout.
- Added existing-session protection, safe-default account switching, and
  confirmed logout.
- Preserved ShellPa's deterministic safety engine as the sole execution
  authority.

### Hardening and acceptance

- Added empty repository, detached head, missing Git, non-repository, bounded
  large status, spaces, and Unicode-path tests.
- Added wheel and source-archive privacy inspection.
- Verified Windows, Ubuntu, and macOS builds with the optional Codex runtime.
- Completed owner-driven Windows terminal acceptance.

## Current quality status

- Ruff formatting: passing
- Ruff linting: passing
- Mypy: passing across 22 source modules
- Pytest: 246 tests passing
- Dependency check: passing
- Wheel and source distribution builds: passing
- Secret and private-file package inspection: passing
- Manual Windows terminal test: passing

## Next direction

No v0.4 feature scope is committed yet. Public repository preparation,
TestPyPI, clean-environment installation testing, and PyPI publication are
separate release activities and require explicit owner approval.

## Distribution plan

ShellPa remains private at the v0.3 checkpoint. If public distribution is
approved later:

1. review the public repository content and license;
2. reserve and verify the package name;
3. publish a release candidate to TestPyPI;
4. test installation in clean Windows, Linux, and macOS environments;
5. make the GitHub repository public if approved;
6. publish the stable package to PyPI.
