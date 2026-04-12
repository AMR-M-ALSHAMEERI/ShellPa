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
*(If Windows gives you an Execution Policy error, run `Set-ExecutionPolicy Unrestricted -Scope CurrentUser` first).*

### 3. Install Dependencies
```bash
# Install the required libraries (Typer, Rich, LiteLLM, Pydantic)
pip install -r requirements.txt

# Install the ShellPa tool locally so the `shellpa` command works globally
pip install -e .
```

### 4. Configure API Keys
ShellPa includes an interactive, arrow-key onboarding wizard to securely set up your API keys and preferred AI model. 
Simply run the CLI for the first time, and it will guide you through choosing OpenRouter, OpenAI, Google Gemini, or Anthropic!

## 🚀 Usage

Once installed, simply run the command from any directory:
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
- Try a dry-run to see the formatting without executing:
  `shellpa "list my desktop files" --dry-run`
- Force execution without approval:
  `shellpa "echo 'Hello'" --force`

## 🛠 Troubleshooting (Mac Specific)
- **"command not found: shellpa"**: Ensure your `venv` is activated. If it still fails, ensure you ran `pip install -e .` with the dot at the end!
- **LiteLLM AuthenticationError**: Check that your `.env` starts with exactly `OPENROUTER_API_KEY=` or `OPENAI_API_KEY=` and has no quotes around the key itself.
- **Python version issues**: ShellPa requires Python 3.10+. If your Mac defaults to python 2.7, make sure to explicitly use `python3` and `pip3` during setup.
