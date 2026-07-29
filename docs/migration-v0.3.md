# Migrating to ShellPa 0.3

ShellPa 0.3 preserves the v0.2 safety, execution, and interactive contracts
while adding workspace awareness and an optional Codex provider.

Reinstall the editable project so the command and dependencies match the new
version:

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[codex]"
```

The `codex` extra is optional. Existing OpenRouter, OpenAI API, Gemini, and
Anthropic configurations continue to work without it.

Verify the installation:

```powershell
shellpa version
shellpa doctor
shellpa context
```

## Workspace behavior

- ShellPa establishes a bounded workspace root.
- It detects allowlisted project markers, known tools, Git state and counts,
  and the active Python environment.
- `shellpa context` shows local facts separately from the provider-safe
  summary.
- The provider-safe summary can influence command generation and recovery.
- Source contents, secret-file contents, and Git filenames are not included.

## Codex subscription provider

Run `shellpa config` and select **OpenAI Codex (ChatGPT subscription)**.
If the optional SDK is missing, the interactive wizard can install its pinned
runtime after explicit approval. A separate Codex CLI installation is not
required.

Use:

```powershell
shellpa login
shellpa login --device-code
shellpa logout
```

Codex manages the ChatGPT session. ShellPa does not read or store the
credentials. Re-running login while connected defaults to keeping the current
session, and logout requires explicit confirmation.

## Distribution status

Version 0.3 is a private repository checkpoint. It is not a public GitHub
release and is not published to PyPI.
