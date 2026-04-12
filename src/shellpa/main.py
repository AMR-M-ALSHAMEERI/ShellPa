import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.live import Live
import pyfiglet
import time
import random
from datetime import datetime
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

def play_startup_animation():
    # Generate an ASCII art banner for "SHELLPA"
    banner_text = pyfiglet.figlet_format("SHELLPA", font="slant")
    # Append the version to the end of the ASCII art exactly, pulling it together
    banner_text = f"{banner_text.rstrip()}  v{__version__}\n"
    
    # helper for appending authors right under the logo
    def append_authors(text_obj):
        text_obj.append(f"  Developed by ", style="bold #00ccff")
        text_obj.append("AMR", style="bold #000066") # Dark blue
        text_obj.append(" & ", style="bold #00ccff")
        text_obj.append("KHADIGA\n\n", style="bold #4b0082") # Dark purple
    
    # Time-based Greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning!"
    elif hour < 17:
        greeting = "Good afternoon!"
    else:
        greeting = "Good evening!"

    # Dynamic Subtitles Pool
    subtitles = [
        "Your AI CLI Assistant.",
        "Navigating the terminal so you don't have to.",
        "Translating thoughts into commands.",
        "Command line magic, automated.",
        "From English to Binary in seconds."
    ]
    
    # Follow-up questions
    questions = [
        "How can I help you today?",
        "What is on your mind?",
        "What shall we execute?",
        "Ready for your next command.",
        "What are we building today?",
        "How can I assist your workflow?"
    ]
    
    # Pick random components and combine them
    selected_subtitle = f"{greeting} {random.choice(subtitles)} {random.choice(questions)}"

    # Ocean/Blue theme colors (Blues + Dark Green)
    aurora_colors = [
        "#001133", # Deep dark blue
        "#002244", # Dark navy
        "#003366", # Navy
        "#004d00", # Dark Green (as requested)
        "#0055ff", # Royal blue
        "#0088ff", # Bright blue
        "#00ccff"  # Light cyan/blue
    ]
    
    # "Breathing Light Blue" theme colors (Settling phase)
    breathing_blues = [
        "#0033cc", "#0055ff", "#0077ff", "#0099ff", 
        "#00bbff", "#00ddff", "#00ffff", "#e6ffff"
    ]
    
    console.print()  # Visual padding
    
    with Live(refresh_per_second=24, transient=False) as live:
        # Step 1: Rapid Aurora Cycle (Extended length: loops 3 times, slightly slower)
        cycling_aurora = aurora_colors + aurora_colors[::-1]
        for _ in range(3):
            for color in cycling_aurora:
                styled_text = Text(banner_text, style=color)
                append_authors(styled_text)
                # We keep the subtitles hidden during the flash
                live.update(styled_text)
                time.sleep(0.07) # Longer delay

        # Step 2: Subtitle Reveal (Typewriter Effect with animated CLI cursor block)
        typed_subtitle = ""
        for char in selected_subtitle:
            typed_subtitle += char
            styled_text = Text(banner_text, style="#0055ff") # Darker blue base
            append_authors(styled_text)
            styled_text.append(f"  {typed_subtitle}", style="italic #00ffff")
            styled_text.append("█", style="blink #00ffff") # CLI cursor block
            live.update(styled_text)
            time.sleep(0.06) # Slower so it lasts
        
        # Step 3: Breathing Light Blue Phase (Extended length: breathes 4 times)
        cycling_blues = breathing_blues + breathing_blues[::-1]
        step = 0
        for _ in range(4):  # Breathe in and out 4 times
            for color in cycling_blues:
                # Animate a flickering terminal underscore/block at the end instead of an emoji
                cursor = "█" if (step % 4 < 2) else "_"
                step += 1
                
                styled_text = Text(banner_text, style=color)
                append_authors(styled_text)
                styled_text.append(f"  {selected_subtitle} ", style=f"italic {color}")
                styled_text.append(cursor, style=f"bold {color}")
                live.update(styled_text)
                time.sleep(0.06) # Slower breathing, lasts longer
        
        # Final Setting State: Bright Icy Blue with a terminal underscore
        final_color = "#00eeff"
        styled_text = Text(banner_text, style=final_color)
        append_authors(styled_text)
        styled_text.append(f"  {selected_subtitle} _", style=f"italic {final_color}")
        live.update(styled_text)

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
    play_startup_animation()
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
