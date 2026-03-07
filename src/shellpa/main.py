import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

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

@app.command()
def do(
    query: str = typer.Argument(..., help="The natural language task you want to perform."),
    force: bool = typer.Option(False, "--force", "-f", help="Execute without asking for confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the generated command without executing it.")
):
    """
    Translate English into a shell command and execute it.
    """
    # Load env variables (API Keys)
    load_config()

    # 1. Detect environment
    env_info = detect_environment()
    
    # 2. Call LLM to generate the command
    with console.status("[bold cyan]Generating command...[/bold cyan]", spinner="dots"):
        try:
            response = generate_command(query, env_info)
        except Exception as e:
            console.print(f"[bold red]Failed to generate command:[/] {e}")
            raise typer.Exit(code=1)

    proposed_command = response.command
    explanation = response.explanation
    
    lexer_name = "powershell" if env_info["shell"] in ["powershell", "cmd"] else "bash"
    
    console.print(f"[bold cyan]Task:[/bold cyan] {query}")
    console.print(f"[bold magenta]Detected Environment:[/bold magenta] {env_info['os']} ({env_info['shell']})\n")
    
    # 3. Display the command using Rich Syntax Highlighting
    syntax = Syntax(proposed_command, lexer_name, theme="monokai", line_numbers=False)
    panel = Panel(syntax, title="Proposed Command", border_style="green")
    console.print(panel)
    console.print(f"[bold blue]Explanation:[/bold blue] {explanation}\n")
    
    # 4. Handle execution modes
    if dry_run:
        console.print("[yellow]Dry-run mode active. Exiting without execution.[/yellow]")
        raise typer.Exit()
        
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

if __name__ == "__main__":
    app()
