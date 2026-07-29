# Migrating to ShellPa 0.2

ShellPa 0.2 keeps the existing `shellpa "<request>"` workflow. Reinstall the
editable package from the project directory so the CLI entry point and
dependencies match the new version:

```powershell
.\venv\Scripts\python.exe -m pip install -e .
```

Then verify the installation:

```powershell
.\venv\Scripts\shellpa.exe version
.\venv\Scripts\shellpa.exe doctor
```

## Behavior changes

- Safety decisions are deterministic and are made after generation, not by the
  language model.
- Critical operations are manual-only. `--force` does not override them.
- `shellpa config`, `doctor`, `about`, `help`, and `version` are real commands.
  If a natural-language request begins with one of those words, use
  `shellpa run "<request>"`.
- Local secret-free diagnostic metadata is enabled by default. Set
  `SHELLPA_LOGGING=0` if no local event log is desired.
- Configuration remains supported in a project `.env` or the user-level
  `~/.shellpa.env` file. Neither file should be committed.
