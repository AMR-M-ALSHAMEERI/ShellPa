import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .os_detect import detect_environment

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
    # 1. Detect environment
    env_info = detect_environment()
    
    # Placeholder: Call LLM module here later
    # For boilerplate, we'll mock the response
    mock_command = "Write-Output 'Hello from ShellPa'" if env_info["shell"] == "powershell" else "echo 'Hello from ShellPa'"
    explanation = "This command prints a greeting to the terminal."
    
    lexer_name = "powershell" if env_info["shell"] in ["powershell", "cmd"] else "bash"
    
    console.print(f"[bold cyan]Task:[/bold cyan] {query}")
    console.print(f"[bold magenta]Detected Environment:[/bold magenta] {env_info['os']} ({env_info['shell']})\n")
    
    # 2. Display the command using Rich Syntax Highlighting
    syntax = Syntax(mock_command, lexer_name, theme="monokai", line_numbers=False)
    panel = Panel(syntax, title="Proposed Command", border_style="green")
    console.print(panel)
    console.print(f"[bold blue]Explanation:[/bold blue] {explanation}\n")
    
    # 3. Handle execution modes
    if dry_run:
        console.print("[yellow]Dry-run mode active. Exiting without execution.[/yellow]")
        raise typer.Exit()
        
    if force:
        console.print("[bold red]WARNING: --force flag used. Executing immediately.[/bold red]")
        execute_command(mock_command, env_info)
    else:
        # Confirmation Step
        confirm = typer.confirm("Do you want to execute this command?", default=False)
        if confirm:
            execute_command(mock_command, env_info)
        else:
            console.print("[yellow]Execution cancelled by user.[/yellow]")

def execute_command(command: str, env_info: dict):
    """
    Placeholder for actual subprocess execution logic.
    """
    console.print("[bold green]Executing...[/bold green]")
    # TODO: Implement subprocess.run in executor.py
    console.print(f"Mock executed: {command}")

if __name__ == "__main__":
    app()
