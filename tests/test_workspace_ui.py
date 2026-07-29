from io import StringIO
from pathlib import Path

from rich.console import Console

from shellpa.models import (
    GitContext,
    ProjectType,
    PythonEnvironmentContext,
    PythonEnvironmentKind,
    WorkspaceBoundarySource,
    WorkspaceContext,
)
from shellpa.workspace_ui import (
    display_workspace_context,
    format_workspace_identity,
)


def workspace_context(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(
        root=tmp_path,
        current_directory=tmp_path / "src",
        boundary_source=WorkspaceBoundarySource.GIT,
        project_types=[ProjectType.DOCKER, ProjectType.PYTHON],
        markers=["Dockerfile", "pyproject.toml"],
        available_tools=["docker", "git", "python"],
        git=GitContext(
            is_repository=True,
            branch="main",
            has_tracked_changes=True,
            has_untracked_files=True,
            tracked_change_count=2,
            untracked_file_count=1,
        ),
        python_environment=PythonEnvironmentContext(
            active=True,
            kind=PythonEnvironmentKind.VENV,
        ),
    )


def test_workspace_identity_is_compact_and_filename_free(tmp_path: Path) -> None:
    identity = format_workspace_identity(workspace_context(tmp_path))

    assert identity == "Docker + Python · Git main* (3) · venv"
    assert str(tmp_path) not in identity


def test_workspace_display_separates_local_paths_from_provider_summary() -> None:
    output = StringIO()
    console = Console(file=output, width=120, color_system=None)
    local_root = Path("local-only-workspace")

    display_workspace_context(console, workspace_context(local_root))

    rendered = output.getvalue()
    assert "ShellPa workspace context" in rendered
    assert str(local_root) in rendered
    assert "Provider-safe summary" in rendered
    provider_section = rendered.split("Provider-safe summary", maxsplit=1)[1]
    assert str(local_root) not in provider_section
    assert "Project types: docker, python" in provider_section
    assert "Git changes: 2 tracked, 1 untracked" in provider_section
