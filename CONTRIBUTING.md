# Contributing to ShellPa

Thank you for helping improve ShellPa. Changes should preserve its central
contract: the model may propose a command, but deterministic local policy and
the user remain in control of execution.

## Development setup

ShellPa requires Python 3.10 or newer.

```bash
git clone https://github.com/AMR-M-ALSHAMEERI/ShellPa.git
cd ShellPa
python -m venv venv
```

Activate the environment:

```bash
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev,codex]"
```

## Before submitting a change

Run the complete local quality gate:

```bash
python -m pytest
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m build
python scripts/verify_package_contents.py dist
```

Changes to command classification or execution behavior should include tests
for Windows and POSIX shells. Changes involving credentials, diagnostics,
workspace context, or recovery must also include a test showing that sensitive
data is not retained or sent to a provider.

## Pull requests

Keep each pull request focused and explain:

- what behavior changes;
- why the change is needed;
- how it was tested;
- any safety, privacy, or cross-platform implications.

Do not commit `.env` files, credentials, local environments, generated package
artifacts, caches, or private planning documents.

