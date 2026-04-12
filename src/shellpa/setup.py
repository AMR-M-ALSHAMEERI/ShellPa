import os
from pathlib import Path
import questionary
from rich.console import Console
import pyfiglet
import time

console = Console()

# Defined styled theme matching our Ocean/Aurora aesthetics
ocean_theme = questionary.Style([
    ('qmark', 'fg:#00ffff bold'),       # Cyan question mark
    ('question', 'fg:#ffffff bold'),    # White question text
    ('answer', 'fg:#00ccff bold'),      # Light blue selected answer
    ('pointer', 'fg:#00ffff bold'),     # Cyan pointer
    ('highlighted', 'fg:#0055ff bold'), # Royal blue for highlighted choice
    ('selected', 'fg:#00ccff'),         # Cyan for selected items in list
    ('separator', 'fg:#003366'),        # Navy blue separator
    ('instruction', 'fg:#0077ff'),      # Instruction text
    ('text', 'fg:#ffffff')              # Normal text
])

def get_env_path() -> Path:
    """Return the global configuration path"""
    return Path.home() / ".shellpa.env"

def run_setup_wizard():
    console.print()
    banner_text = pyfiglet.figlet_format("SHELLPA", font="slant")
    console.print(f"[bold #00ccff]{banner_text}[/bold #00ccff]")
    
    console.print("[bold cyan]Welcome to ShellPa Setup Wizard! 🚀[/bold cyan]")
    console.print("[dim]Let's configure your AI provider and model.[/dim]\n")
    
    # 1. Choose Provider
    provider = questionary.select(
        "Select your AI Provider:",
        choices=[
            questionary.Choice("OpenRouter (Recommended)", value="openrouter"),
            questionary.Choice("OpenAI", value="openai"),
            questionary.Choice("Google Gemini", value="gemini"),
            questionary.Choice("Anthropic", value="anthropic")
        ],
        style=ocean_theme
    ).ask()
    
    if not provider:
        console.print("[red]Setup cancelled.[/red]")
        return False
        
    # 2. Choose Model based on provider
    model_choices = []
    if provider == "openrouter":
        model_choices = [
            questionary.Choice("openai/gpt-3.5-turbo (Recommended)", value="openrouter/openai/gpt-3.5-turbo"),
            questionary.Choice("anthropic/claude-3-haiku", value="openrouter/anthropic/claude-3-haiku"),
            questionary.Choice("google/gemini-flash-1.5", value="openrouter/google/gemini-flash-1.5")
        ]
    elif provider == "openai":
        model_choices = [
            "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"
        ]
    elif provider == "gemini":
        model_choices = [
            "gemini/gemini-1.5-pro", "gemini/gemini-1.5-flash", "gemini/gemini-pro"
        ]
    elif provider == "anthropic":
        model_choices = [
            "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"
        ]
        
    model_choices.append(questionary.Choice("Custom Model...", value="custom"))

    model = questionary.select(
        "Select the model:",
        choices=model_choices,
        style=ocean_theme
    ).ask()
    
    if not model:
        return False
        
    if model == "custom":
        model = questionary.text(
            "Enter your custom model string (e.g. ollama/mistral):",
            style=ocean_theme
        ).ask()
        if not model:
            return False

    # 3. Enter API Key
    api_key_name = ""
    if provider == "openrouter":
        api_key_name = "OPENROUTER_API_KEY"
    elif provider == "openai":
        api_key_name = "OPENAI_API_KEY"
    elif provider == "gemini":
        api_key_name = "GEMINI_API_KEY"
    elif provider == "anthropic":
        api_key_name = "ANTHROPIC_API_KEY"
        
    api_key = questionary.password(
        f"Enter your {provider.capitalize()} API Key:",
        style=ocean_theme
    ).ask()
    
    if not api_key:
        return False
        
    # Save to global config
    env_path = get_env_path()
    
    # Read existing if any
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env_vars[k] = v
                    
    # Update config
    env_vars["SHELLPA_MODEL"] = model
    env_vars[api_key_name] = api_key
    
    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
            
    # Load into current environment immediately
    os.environ["SHELLPA_MODEL"] = model
    os.environ[api_key_name] = api_key
    
    console.print("\n[bold green]Configuration saved successfully! ✨[/bold green]")
    with console.status("[bold cyan]Initializing AI Agent...[/bold cyan]", spinner="dots"):
        time.sleep(1.5)  # small pause for visual feedback
        
    return True