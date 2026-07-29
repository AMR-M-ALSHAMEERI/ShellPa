from pathlib import Path

from shellpa.models import ProjectType, WorkspaceBoundarySource
from shellpa.workspace import (
    detect_workspace,
    format_provider_workspace_summary,
    resolve_workspace_boundary,
)


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_current_directory_is_boundary_without_markers(tmp_path: Path) -> None:
    nested = tmp_path / "plain" / "nested"
    nested.mkdir(parents=True)

    context = detect_workspace(nested)

    assert context.root == nested.resolve()
    assert context.boundary_source is WorkspaceBoundarySource.CURRENT_DIRECTORY
    assert context.project_types == []
    assert context.markers == []


def test_nearest_project_marker_defines_non_git_boundary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "src" / "package"
    nested.mkdir(parents=True)
    touch(project / "pyproject.toml")

    root, source = resolve_workspace_boundary(nested)

    assert root == project.resolve()
    assert source is WorkspaceBoundarySource.PROJECT_MARKER


def test_enclosing_git_root_takes_priority_over_nested_marker(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested_project = repository / "packages" / "tool"
    nested_project.mkdir(parents=True)
    (repository / ".git").mkdir()
    touch(nested_project / "pyproject.toml")

    context = detect_workspace(nested_project)

    assert context.root == repository.resolve()
    assert context.boundary_source is WorkspaceBoundarySource.GIT
    assert context.project_types == []


def test_detects_multiple_project_types_from_allowlisted_names(
    tmp_path: Path,
) -> None:
    touch(tmp_path / "pyproject.toml")
    touch(tmp_path / "package.json")
    touch(tmp_path / "Dockerfile")

    context = detect_workspace(tmp_path)

    assert context.project_types == [
        ProjectType.DOCKER,
        ProjectType.NODE,
        ProjectType.PYTHON,
    ]
    assert context.markers == ["Dockerfile", "package.json", "pyproject.toml"]


def test_detection_does_not_descend_into_child_projects(tmp_path: Path) -> None:
    touch(tmp_path / "child" / "package.json")

    context = detect_workspace(tmp_path)

    assert context.root == tmp_path.resolve()
    assert context.project_types == []
    assert context.markers == []


def test_secret_like_files_are_not_workspace_markers(tmp_path: Path) -> None:
    touch(tmp_path / ".env")
    touch(tmp_path / "credentials.json")
    touch(tmp_path / "private.key")

    context = detect_workspace(tmp_path)

    assert context.project_types == []
    assert context.markers == []


def test_provider_summary_contains_metadata_but_not_absolute_paths(
    tmp_path: Path,
) -> None:
    touch(tmp_path / "pyproject.toml")
    context = detect_workspace(tmp_path)

    summary = format_provider_workspace_summary(context)

    assert "Workspace boundary: project_marker" in summary
    assert "Project types: python" in summary
    assert "Markers: pyproject.toml" in summary
    assert str(tmp_path.resolve()) not in summary
