# ShellPa command reference

Run `shellpa` with no arguments to open the interactive session.

## Commands

| Command | Purpose |
| --- | --- |
| `shellpa run "<request>"` | Translate and process a natural-language request. |
| `shellpa config` | Configure the provider, model, and credential. |
| `shellpa doctor` | Inspect the local installation without displaying secrets. |
| `shellpa doctor --online` | Also check provider-host reachability without a model request or credential. |
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

## Local diagnostic log

ShellPa stores minimal troubleshooting events in
`~/.shellpa/logs/shellpa.jsonl`. Events include timings, risk level, exit status,
and platform metadata. They exclude requests, generated commands, command
output, environment variables, and credentials.

Set `SHELLPA_LOGGING=0` to disable this local log.
