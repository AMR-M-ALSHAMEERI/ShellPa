# Installing and managing ShellPa

ShellPa requires Python 3.10 or newer. `pipx` is the recommended installer for
the command-line application because it gives ShellPa an isolated environment
while exposing the `shellpa` command on the user's `PATH`.

## Install pipx

### Windows

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Close and reopen the terminal after `ensurepath`.

### macOS

```bash
brew install pipx
pipx ensurepath
```

### Ubuntu 23.04 or newer

```bash
sudo apt update
sudo apt install pipx
pipx ensurepath
```

### Fedora

```bash
sudo dnf install pipx
pipx ensurepath
```

For other Linux distributions:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

Distribution packages are preferable on systems that enforce PEP 668 and
reject user-level installation into the system Python.

## Install ShellPa

Standard providers:

```bash
pipx install shellpa
```

Include ChatGPT subscription access through the embedded Codex provider:

```bash
pipx install "shellpa[codex]"
```

Then configure and start ShellPa:

```bash
shellpa config
shellpa
```

## pip fallback

If `pipx` cannot be used, install into the user environment:

```bash
python -m pip install --user shellpa
```

This fallback provides less dependency isolation than `pipx` and may require
adding the Python user scripts directory to `PATH`.

## Update

```bash
pipx upgrade shellpa
```

For a pip-managed installation:

```bash
python -m pip install --user --upgrade shellpa
```

## Uninstall

```bash
pipx uninstall shellpa
```

For a pip-managed installation:

```bash
python -m pip uninstall shellpa
```

Uninstalling the application does not automatically delete user-approved
settings, local diagnostic logs, operating-system credential entries, or the
Codex-managed ChatGPT session. A guided lifecycle cleanup flow is planned for a
later release.
