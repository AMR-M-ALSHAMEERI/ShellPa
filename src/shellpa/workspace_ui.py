"""Transparent terminal presentation for ShellPa workspace metadata."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import WorkspaceContext
from .workspace import format_provider_workspace_summary


def format_workspace_identity(context: WorkspaceContext) -> str:
    """Build a compact, filename-free identity for interactive status."""
    project_label = (
        " + ".join(project_type.value.title() for project_type in context.project_types)
        if context.project_types
        else "Workspace"
    )
    parts = [project_label]

    if context.git.is_repository:
        git_label = context.git.branch or context.git.head_state.value
        change_count = (
            context.git.tracked_change_count + context.git.untracked_file_count
        )
        if change_count:
            git_label += f"* ({change_count})"
        parts.append(f"Git {git_label}")

    if context.python_environment.active and context.python_environment.kind:
        parts.append(context.python_environment.kind.value)
    return " · ".join(parts)


def display_workspace_identity(console: Console, context: WorkspaceContext) -> None:
    """Show the compact identity once when an interactive session starts."""
    console.print(
        Text(f"Workspace · {format_workspace_identity(context)}", style="dim")
    )
    console.print()


def display_workspace_context(console: Console, context: WorkspaceContext) -> None:
    """Show local details and the exact provider-safe summary separately."""
    table = Table(
        title="ShellPa workspace context",
        show_header=False,
        pad_edge=False,
    )
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    table.add_row("Workspace root", str(context.root))
    table.add_row("Current directory", str(context.current_directory))
    table.add_row("Boundary", context.boundary_source.value.replace("_", " "))
    table.add_row(
        "Project types",
        ", ".join(project_type.value for project_type in context.project_types)
        or "Unclassified",
    )
    table.add_row("Markers", ", ".join(context.markers) or "None")
    table.add_row("Available tools", ", ".join(context.available_tools) or "None")

    if context.git.is_repository:
        head = context.git.branch or context.git.head_state.value
        table.add_row("Git HEAD", head)
        bounded = " (bounded)" if context.git.status_truncated else ""
        table.add_row(
            "Git changes",
            f"{context.git.tracked_change_count} tracked, "
            f"{context.git.untracked_file_count} untracked{bounded}",
        )
    else:
        table.add_row("Git", "Not detected")

    if context.python_environment.active and context.python_environment.kind:
        table.add_row(
            "Python environment",
            f"{context.python_environment.kind.value} (active)",
        )
    else:
        table.add_row("Python environment", "Not active")

    if context.warnings:
        table.add_row("Warnings", "\n".join(context.warnings))

    console.print(table)
    console.print(
        Panel(
            Text(format_provider_workspace_summary(context)),
            title="Provider-safe summary",
            subtitle="Only these workspace facts may be sent to a configured provider",
            border_style="cyan",
        )
    )
