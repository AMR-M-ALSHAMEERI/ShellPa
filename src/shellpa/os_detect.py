import os
import platform
from typing import Dict, Any

def detect_environment() -> Dict[str, Any]:
    """
    Detects the current operating system and specific shell environment.
    Returns a dictionary with 'os', 'shell', and additional context.
    """
    system = platform.system()
    
    env_info = {
        "os": system,
        "shell": "unknown",
        "is_windows": system == "Windows",
        "is_mac": system == "Darwin",
        "is_linux": system == "Linux"
    }

    if env_info["is_windows"]:
        # On Windows, check if we are in PowerShell or CMD
        # PowerShell sets PSModulePath
        ps_module_path = os.environ.get("PSModulePath", "")
        if ps_module_path:
            env_info["shell"] = "powershell"
        else:
            comspec = os.environ.get("COMSPEC", "").lower()
            if "cmd.exe" in comspec:
                env_info["shell"] = "cmd"
            elif "pwsh" in comspec or "powershell" in comspec:
                env_info["shell"] = "powershell"
            else:
                env_info["shell"] = "cmd" # Default fallback for Windows
                
    elif env_info["is_mac"] or env_info["is_linux"]:
        # On POSIX systems, check the $SHELL environment variable
        shell_var = os.environ.get("SHELL", "").lower()
        if "zsh" in shell_var:
            env_info["shell"] = "zsh"
        elif "bash" in shell_var:
            env_info["shell"] = "bash"
        elif "fish" in shell_var:
            env_info["shell"] = "fish"
        else:
            # Default fallback for POSIX
            env_info["shell"] = "zsh" if env_info["is_mac"] else "bash"

    return env_info

def get_system_prompt_context() -> str:
    """
    Returns a formatted string suitable for an LLM system prompt
    describing the user's current OS and shell.
    """
    env_info = detect_environment()
    return f"Operating System: {env_info['os']}\nShell Environment: {env_info['shell']}"
