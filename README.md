# ShellPa

A cross-platform CLI Agent for performing system tasks via natural language.
ShellPa automatically detects if you are using Windows (cmd/PowerShell) or macOS/Linux (zsh/bash) and translates English instructions into exactly the right terminal dialect.

## Setup (Mac / Linux / Windows)

Welcome to ShellPa project! Follow these exact steps to clone the repo, install the dependencies, and get the agent running on your local machine.

### 1. Clone & Setup Virtual Environment
```bash
git clone <repository_url>
cd shellpa

# Create the virtual environment
python3 -m venv venv
or
py -m venv venv
```

### 2. Activate the Environment
You must activate the environment every time you open a new terminal to work on this project.

**Mac / Linux (zsh or bash):**
```bash
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```
*(If Windows blocks activation, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then try again.)*

### 3. Install Dependencies
```bash
# Install the required libraries (Typer, Rich, LiteLLM, Pydantic)
pip install -r requirements.txt

# Install ShellPa into the active project environment
pip install -e .
```

### 4. Configure a Provider
ShellPa includes an interactive, arrow-key wizard for choosing OpenRouter,
OpenAI, Google Gemini, Anthropic, or the optional OpenAI Codex provider for
eligible ChatGPT subscriptions.

```bash
shellpa config
```

API-backed providers request their corresponding API key. The Codex
subscription provider does not request an OpenAI API key. If its embedded SDK
is missing, ShellPa can install the pinned provider after explicit approval and
then offer browser or device-code sign-in.

## Usage

Once installed and the project environment is active, run:
```bash
shellpa "Find all python files in this project"
```

If you don't provide a prompt, it drops you into our beautiful interactive REPL mode!
```bash
shellpa
```

### Extra Commands:
- Change your Model or Provider later:
  `shellpa config`
- Inspect workspace facts and the provider-safe summary:
  `shellpa context`
- Connect a ChatGPT account for the Codex provider:
  `shellpa login`
- Review or clear the Codex-managed account session:
  `shellpa logout`
- Check the installation, provider, Codex account state, and environment:
  `shellpa doctor`
- View developer info and explore their GitHub interactive profiles via `webbrowser`:
  `shellpa about`
- Try a dry-run to see the formatting without executing:
  `shellpa "list my desktop files" --dry-run`
- Force execution without approval:
  `shellpa "echo 'Hello'" --force`

## Troubleshooting
- **"command not found: shellpa"**: Ensure your `venv` is activated. If it still fails, ensure you ran `pip install -e .` with the dot at the end!
- **LiteLLM AuthenticationError**: Check that your `.env` starts with exactly `OPENROUTER_API_KEY=` or `OPENAI_API_KEY=` and has no quotes around the key itself.
- **Codex is signed out**: Run `shellpa login`, or use
  `shellpa login --device-code` if a browser callback is unavailable.
- **Python version issues**: ShellPa requires Python 3.10+. If your Mac defaults to python 2.7, make sure to explicitly use `python3` and `pip3` during setup.

## Workspace Privacy

ShellPa detects bounded workspace metadata such as project type, known tools,
Git state and change counts, and the active Python environment. It does not read
source contents, `.env` contents, credential files, or arbitrary Git filenames
to create the provider-safe workspace summary. Run `shellpa context` to inspect
exactly what ShellPa knows and what may influence generation.
