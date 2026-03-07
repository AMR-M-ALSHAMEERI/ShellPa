import subprocess
import typer
from rich.console import Console

console = Console()

def execute_command(command: str, env_info: dict):
    """
    Executes the given shell command securely in the user's terminal.
    """
    console.print("\n[bold green]Executing...[/bold green]\n")
    
    try:
        # We set capture_output=False so the output prints directly to the user's standard STDOUT live.
        if env_info["is_windows"]:
            if env_info["shell"] in ["powershell", "pwsh"]:
                # Execute explicitly through PowerShell
                cmd_list = ["powershell.exe", "-NoProfile", "-Command", command]
            else:
                # Execute explicitly through CMD
                cmd_list = ["cmd.exe", "/c", command]
            
            result = subprocess.run(cmd_list, text=True, capture_output=False)
        else:
            # Execute on Mac/Linux
            executable = "/bin/sh"
            if env_info["shell"] == "zsh":
                executable = "/bin/zsh"
            elif env_info["shell"] == "bash":
                executable = "/bin/bash"
                
            cmd_list = [executable, "-c", command]
            result = subprocess.run(cmd_list, text=True, capture_output=False)
            
        if result.returncode != 0:
            console.print(f"\n[bold red]Command exited with status {result.returncode}.[/bold red]")
            raise typer.Exit(code=result.returncode)
    except Exception as e:
        console.print(f"\n[bold red]Error executing command: {e}[/bold red]")
        raise typer.Exit(code=1)
