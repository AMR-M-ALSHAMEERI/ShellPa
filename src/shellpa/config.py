import os
from dotenv import load_dotenv
from pathlib import Path
from .setup import get_env_path, run_setup_wizard
from rich.console import Console

console = Console()

def load_config():
    """Load config from local .env or global ~/.shellpa.env file."""
    # First try local .env
    load_dotenv()
    
    # Then load global ~/.shellpa.env (this overrides if not present locally)
    env_path = get_env_path()
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        
    # Check if a model and API key is set
    model = os.getenv("SHELLPA_MODEL")
    api_key_present = any(k for k in os.environ if "_API_KEY" in k)
    
    # If not configured, trigger the wizard!
    if not model or not api_key_present:
        console.print("[yellow]Initial configuration required...[/yellow]")
        success = run_setup_wizard()
        if not success:
            console.print("[bold red]Error: You must configure ShellPa before using it.[/bold red]")
            exit(1)
