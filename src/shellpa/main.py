import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from typing import Optional

from . import __version__
from .config import load_config
from .os_detect import detect_environment
from .llm import generate_command
from .executor import execute_command

app = typer.Typer(
    name="shellpa",
    help="ShellPa: A cross-platform CLI Agent for natural language system execution.",
    add_completion=False
)
console = Console()

def print_banner():
    # Large ASCII banner natively supporting uppercase SHELLPA
    logo = r"""
  ____  _          _ _  ____       
 / ___|| |__   ___| | ||  _ \ __ _ 
 \___ \| '_ \ / _ \ | || |_) / _` |
  ___) | | | |  __/ | ||  __/ (_| |
 |____/|_| |_|\___|_|_||_|   \__,_|
    """
    console.print(f"[bold cyan]{logo}[/bold cyan]")
    console.print(f"  [bold white]Version:[/bold white] [green]{__version__}[/green]")
    console.print("  [bold magenta]Developed by AMR & KHADIGA[/bold magenta]\n")

def process_query(query: str, env_info: dict, force: bool, dry_run: bool):
    """Processes a single intent-to-command operation natively."""
    with console.status("[bold cyan]Generating command...[/bold cyan]", spinner="dots"):
        try:
            response = generate_command(query, env_info)
        except Exception as e:
            console.print(f"[bold red]Failed to generate command:[/] {e}")
            raise typer.Exit(code=1)

    proposed_command = response.command
    explanation = response.explanation
    
    lexer_name = "powershell" if env_info["shell"] in ["powershell", "cmd"] else "bash"
    
    # console.print(f"[bold cyan]Task:[/bold cyan] {query}")
    # We omit printing the task label redundantly if they just typed it in REPL, 
    # but keep OS metadata and explanation logic intact.
    console.print(f"[bold magenta]Detected Environment:[/bold magenta] {env_info['os']} ({env_info['shell']})\n")
    
    # Display the command using Rich Syntax Highlighting
    syntax = Syntax(proposed_command, lexer_name, theme="monokai", line_numbers=False)
    panel = Panel(syntax, title="Proposed Command", border_style="green")
    console.print(panel)
    console.print(f"[bold blue]Explanation:[/bold blue] {explanation}\n")
    
    # Handle execution modes
    if dry_run:
        console.print("[yellow]Dry-run mode active. Exiting without execution.[/yellow]")
        return
        
    if force:
        console.print("[bold red]WARNING: --force flag used. Executing immediately.[/bold red]")
        execute_command(proposed_command, env_info)
    else:
        # Confirmation Step
        confirm = typer.confirm("Do you want to execute this command?", default=False)
        if confirm:
            execute_command(proposed_command, env_info)
        else:
            console.print("[yellow]Execution cancelled by user.[/yellow]")

@app.command()
def do(
    query: Optional[str] = typer.Argument(None, help="The natural language task you want to perform."),
    force: bool = typer.Option(False, "--force", "-f", help="Execute without asking for confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the generated command without executing it.")
):
    """
    Translate English into a shell command and execute it.
    If no query is provided, starts an interactive REPL session.
    """
    load_config()
    env_info = detect_environment()

    # Onetime Execution
    if query is not None:
        process_query(query, env_info, force, dry_run)
        return

    # REPL Continuous Mode
    print_banner()
    console.print("[dim]Type 'exit' or 'quit' to close the interactive session.[/dim]\n")
    
    while True:
        try:
            user_input = console.input("[bold green]ShellPa > [/bold green]").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                console.print("[bold cyan]Goodbye![/bold cyan]")
                break
            
            # Subprocess/Generate fail logic may throw typer.Exit - we catch it to preserve the Loop.
            try:
                process_query(user_input, env_info, force, dry_run)
            except typer.Exit:
                pass
            
            console.print() # Newline padding for the loop
            
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold cyan]Goodbye![/bold cyan]")
            break

if __name__ == "__main__":
    app()
