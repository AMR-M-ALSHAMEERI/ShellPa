import subprocess
from rich.console import Console

console = Console()

def execute_command(command: str, env_info: dict) -> tuple[bool, str]:
    """
    Executes the given shell command securely in the user's terminal.
    Returns a tuple of (success_status, error_message).
    """
    console.print("\n[bold green]Executing...[/bold green]\n")
    
    try:
        # Determine execution wrapper
        if env_info["os"].lower() == "windows":
            if env_info["shell"] in ["powershell", "pwsh"]:
                cmd_list = ["powershell.exe", "-NoProfile", "-Command", command]
            else:
                cmd_list = ["cmd.exe", "/c", command]
        else:
            executable = "/bin/sh"
            if env_info["shell"] == "zsh":
                executable = "/bin/zsh"
            elif env_info["shell"] == "bash":
                executable = "/bin/bash"
            cmd_list = [executable, "-c", command]
            
        # We capture the output to inspect it for auto-recovery
        result = subprocess.run(cmd_list, text=True, capture_output=True)
        
        # Print standard output if it exists
        if result.stdout.strip():
            print(result.stdout)
            
        if result.returncode != 0:
            # We capture standard error (or standard out, whichever had the print)
            error_msg = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
            if not error_msg:
                error_msg = f"Failed with exit code {result.returncode}."
            return False, error_msg
            
        return True, ""
        
    except Exception as e:
        return False, f"Python Error: {str(e)}"
