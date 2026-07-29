# ShellPa command reference

Run `shellpa` with no arguments to open the interactive session.

## Commands

| Command | Purpose |
| --- | --- |
| `shellpa run "<request>"` | Translate and process a natural-language request. |
| `shellpa config` | Configure the provider, model, and credential. |
| `shellpa login` | Connect a ChatGPT account for the optional Codex provider. |
| `shellpa login --device-code` | Use Codex device-code authentication instead of a browser callback. |
| `shellpa logout` | Review and optionally clear the Codex-managed account session. |
| `shellpa doctor` | Inspect the local installation without displaying secrets. |
| `shellpa doctor --online` | Also check provider-host reachability without a model request or credential. |
| `shellpa context` | Show local workspace facts and the smaller provider-safe summary. |
| `shellpa about` | Open the ShellPa identity and developer hub. |
| `shellpa help` | Show command help. |
| `shellpa version` | Show the installed version. |

The shorter form `shellpa "<request>"` is still supported. Use the explicit
`shellpa run` form when a request begins with a reserved command word, such as
`config`, `doctor`, or `about`.

## Global execution options

- `--mode ask` requests approval before execution.
- `--mode plan` shows the proposal without executing it.
- `--mode trusted` may auto-run only known read-only or normal-risk commands.
- `--dry-run` prevents execution.
- `--force` skips approval only where the safety policy permits it.
- `--timeout SECONDS` limits execution time.
- `--passthrough` connects an interactive child command directly to the terminal.

Critical policy matches remain manual-only in every mode. ShellPa shows the
command so the user can independently review it, but does not provide a switch
that bypasses this boundary.

## Interactive controls

Inside `shellpa`, use `/help` to show all controls. The v0.3 workspace and Codex
controls are:

- `/context` refreshes and displays workspace metadata.
- `/login` connects ChatGPT through Codex.
- `/login device-code` uses a one-time device code.
- `/logout` reviews the current Codex session and requires explicit
  confirmation before sign-out.

`/login` does not need to be run for every ShellPa session. Codex manages and
refreshes its cached authentication session. If an account is already
connected, ShellPa defaults to keeping it and does not display the account
email or identity.

## Workspace transparency

ShellPa detects bounded metadata such as the workspace boundary, allowlisted
project markers, project types, available tools, Git branch/state and change
counts, and the active Python environment. `shellpa context` separates
local-only paths from the smaller summary that may be sent to the configured
provider.

ShellPa does not read source contents, `.env` contents, credential files, or
arbitrary Git filenames to build this summary.

## Local diagnostic log

ShellPa stores minimal troubleshooting events in
`~/.shellpa/logs/shellpa.jsonl`. Events include timings, risk level, exit status,
and platform metadata. They exclude requests, generated commands, command
output, environment variables, and credentials.

Set `SHELLPA_LOGGING=0` to disable this local log.
