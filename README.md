<p align="center">
  <img src="https://raw.githubusercontent.com/AMR-M-ALSHAMEERI/ShellPa/main/docs/assets/shellpa-mark.png" alt="ShellPa command-line logo" width="340">
</p>

<h1 align="center">ShellPa</h1>

<p align="center">
  A safety-conscious, cross-platform terminal assistant.
  Describe the outcome; review the native command; stay in control.
</p>

<p align="center">
  <a href="https://github.com/AMR-M-ALSHAMEERI/ShellPa/actions/workflows/ci.yml"><img src="https://github.com/AMR-M-ALSHAMEERI/ShellPa/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/shellpa/"><img src="https://img.shields.io/pypi/v/shellpa?color=14b8e6" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-071a3d" alt="Windows, Linux, and macOS">
  <a href="https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-C9A24E" alt="MIT License"></a>
</p>

ShellPa translates natural-language intent into a command for the active
operating system and shell. Before anything runs, ShellPa applies a
deterministic local safety policy and presents the proposal for review.

```text
User intent
    -> structured command proposal
    -> deterministic safety assessment
    -> permission decision
    -> observable execution
    -> redacted recovery when needed
```

## Why ShellPa

- **Cross-platform commands** — supports PowerShell, CMD, Bash, and Zsh.
- **Deterministic safety** — the model proposes; ShellPa decides whether a
  command may execute.
- **Interactive terminal UX** — themes, motion settings, history, completion,
  activity states, and keyboard navigation.
- **Workspace awareness** — detects bounded project, Git, tool, and Python
  environment metadata without reading source contents.
- **Provider choice** — supports OpenRouter, OpenAI API, Gemini, Anthropic, and
  eligible ChatGPT subscriptions through the optional Codex provider.
- **Private by design** — diagnostics and recovery exclude credentials,
  environment values, command output, and arbitrary Git filenames.

## Installation

ShellPa requires Python 3.10 or newer. For a standalone command-line
application, `pipx` is recommended because it creates an isolated environment
while making `shellpa` available from any terminal.

```bash
pipx install shellpa
```

For ChatGPT subscription access through the embedded Codex provider:

```bash
pipx install "shellpa[codex]"
```

The configuration wizard can also install the optional Codex provider after
explicit approval. A separate Codex CLI installation is not required.

If `pipx` is not installed, or for platform-specific update and removal
instructions, see the
[installation guide](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/docs/installation.md).

## Quick start

Configure a provider:

```bash
shellpa config
```

Run a natural-language request:

```bash
shellpa "show the five largest files in this directory"
```

Preview without execution:

```bash
shellpa "show the five largest files in this directory" --dry-run
```

Open the interactive session:

```bash
shellpa
```

Inside the session, use `/help` to see all interactive controls.

## Providers

| Provider | Authentication | API billing |
| --- | --- | --- |
| OpenRouter | API key | Provider account |
| OpenAI | OpenAI Platform API key | OpenAI API account |
| Google Gemini | API key | Provider account |
| Anthropic | API key | Provider account |
| OpenAI Codex | Eligible ChatGPT account | ChatGPT plan limits |

The Codex path delegates sign-in and session storage to the official embedded
Codex runtime. ShellPa does not read or store Codex credentials. Existing
sessions are preserved by default, and logout requires explicit confirmation.

For API-backed providers, ShellPa stores newly configured keys in Windows
Credential Locker, macOS Keychain, Linux Secret Service, or KWallet through the
active operating-system credential backend. Existing plaintext user
configuration is migrated only after the secure copy is verified. When secure
storage is unavailable, ShellPa can use a key for the current process without
silently saving another plaintext copy.

```bash
shellpa login
shellpa login --device-code
shellpa logout
```

## Safety model

ShellPa assesses every proposed command locally:

| Level | Typical behavior |
| --- | --- |
| Read-only | May run automatically only in Trusted mode |
| Normal | Requires approval unless safely permitted by explicit `--force` |
| High risk | Requires typed confirmation |
| Critical | Manual-only; ShellPa will not execute it |
| Unknown | Requires review and cannot be silently trusted |

Approved commands inherit operational environment variables needed by the
shell, but ShellPa withholds provider keys, its own configuration variables,
and other secret-shaped values from child processes.

Permission modes:

- **Ask** — review commands before execution.
- **Plan** — display proposals without execution.
- **Trusted** — automatically runs only commands proven read-only.

`--force` does not bypass critical-policy boundaries.

## Workspace transparency

ShellPa detects only bounded workspace facts:

- workspace boundary and allowlisted project markers;
- project types and known executable availability;
- Git branch, detached/unborn state, and change counts;
- active Python environment type.

It does not read source contents, `.env` contents, credential files, or
arbitrary Git filenames to create the provider-safe summary.

```bash
shellpa context
```

The context view clearly separates local-only paths from the smaller summary
that may influence a provider request.

## Useful commands

| Command | Purpose |
| --- | --- |
| `shellpa` | Open the interactive terminal |
| `shellpa "<request>"` | Generate, review, and process a command |
| `shellpa config` | Configure the provider and model |
| `shellpa context` | Inspect workspace facts and provider-safe context |
| `shellpa doctor` | Diagnose the local installation without exposing secrets |
| `shellpa about` | Open the ShellPa identity and project hub |
| `shellpa update` | Check the stable PyPI release and show the appropriate upgrade command |
| `shellpa version` | Show the installed version |

See the complete
[command reference](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/docs/commands.md)
and
[v0.3 migration guide](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/docs/migration-v0.3.md).

## Development

Clone the repository and create a project environment:

```bash
git clone https://github.com/AMR-M-ALSHAMEERI/ShellPa.git
cd ShellPa
python -m venv venv
```

Activate it:

```bash
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

Install the development and Codex extras:

```bash
python -m pip install -e ".[dev,codex]"
```

Run the quality suite:

```bash
python -m pytest
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m build
python scripts/verify_package_contents.py dist
```

See [CONTRIBUTING.md](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/CONTRIBUTING.md)
before proposing a change. Report suspected vulnerabilities through the
[security policy](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/SECURITY.md),
not through a public issue.

## License

ShellPa is available under the
[MIT License](https://github.com/AMR-M-ALSHAMEERI/ShellPa/blob/main/LICENSE).

## Release status

Version 0.3.0 is available on [PyPI](https://pypi.org/project/shellpa/0.3.0/).
It was published through the protected Trusted Publishing workflow after
TestPyPI and clean-install validation.
