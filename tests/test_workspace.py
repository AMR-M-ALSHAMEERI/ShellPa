import subprocess
from pathlib import Path

import pytest

import shellpa.workspace as workspace
from shellpa.models import (
    GitHeadState,
    ProjectType,
    PythonEnvironmentKind,
    WorkspaceBoundarySource,
)
from shellpa.workspace import (
    detect_available_tools,
    detect_git_context,
    detect_python_environment,
    detect_workspace,
    format_provider_workspace_summary,
    resolve_workspace_boundary,
)


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )


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


def test_detect_available_tools_uses_lookup_without_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = {"git", "python", "uv"}
    looked_up: list[str] = []

    def fake_which(executable: str) -> str | None:
        looked_up.append(executable)
        return executable if executable in discovered else None

    monkeypatch.setattr(workspace.shutil, "which", fake_which)

    assert detect_available_tools() == ["git", "python", "uv"]
    assert {"git", "python", "uv", "docker"}.issubset(looked_up)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"CONDA_PREFIX": "private-path"}, PythonEnvironmentKind.CONDA),
        ({"PIPENV_ACTIVE": "1"}, PythonEnvironmentKind.PIPENV),
        ({"POETRY_ACTIVE": "1"}, PythonEnvironmentKind.POETRY),
        ({"VIRTUAL_ENV": "private-path"}, PythonEnvironmentKind.VENV),
    ],
)
def test_python_environment_uses_variable_names_not_values(
    environment: dict[str, str],
    expected: PythonEnvironmentKind,
) -> None:
    context = detect_python_environment(
        environment,
        prefix="same",
        base_prefix="same",
    )

    assert context.active is True
    assert context.kind is expected
    assert "private-path" not in context.model_dump_json()


def test_python_environment_detects_interpreter_prefix() -> None:
    context = detect_python_environment({}, prefix="venv", base_prefix="base")

    assert context.active is True
    assert context.kind is PythonEnvironmentKind.VENV


def test_python_environment_can_be_inactive() -> None:
    context = detect_python_environment({}, prefix="same", base_prefix="same")

    assert context.active is False
    assert context.kind is None


def test_porcelain_parser_counts_without_retaining_names() -> None:
    tracked, untracked, truncated = workspace._parse_porcelain_status(
        b" M secret-name.py\0?? private-file.txt\0R  new-name.py\0old-name.py\0",
        truncated=False,
    )

    assert tracked == 2
    assert untracked == 1
    assert truncated is False


def test_porcelain_parser_caps_large_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workspace, "MAX_GIT_STATUS_ENTRIES", 2)

    tracked, untracked, truncated = workspace._parse_porcelain_status(
        b" M first\0?? second\0?? third\0",
        truncated=False,
    )

    assert tracked == 1
    assert untracked == 1
    assert truncated is True


def test_git_context_reports_branch_and_change_counts(tmp_path: Path) -> None:
    if workspace.shutil.which("git") is None:
        pytest.skip("Git is unavailable.")

    run_git(tmp_path, "init", "--quiet")
    run_git(tmp_path, "config", "user.email", "shellpa@example.invalid")
    run_git(tmp_path, "config", "user.name", "ShellPa Tests")
    tracked_file = tmp_path / "tracked-secret-name.txt"
    tracked_file.write_text("original", encoding="utf-8")
    run_git(tmp_path, "add", "tracked-secret-name.txt")
    run_git(tmp_path, "commit", "--quiet", "-m", "initial")
    tracked_file.write_text("modified", encoding="utf-8")
    (tmp_path / "untracked-private-name.txt").write_text("new", encoding="utf-8")

    context, warning = detect_git_context(tmp_path, git_available=True)

    assert warning is None
    assert context.is_repository is True
    assert context.branch
    assert context.head_state is GitHeadState.BRANCH
    assert context.has_tracked_changes is True
    assert context.has_untracked_files is True
    assert context.tracked_change_count == 1
    assert context.untracked_file_count == 1

    summary = format_provider_workspace_summary(
        detect_workspace(tmp_path),
    )
    assert "tracked-secret-name.txt" not in summary
    assert "untracked-private-name.txt" not in summary
    assert str(tmp_path.resolve()) not in summary


def test_git_context_degrades_when_git_is_missing(tmp_path: Path) -> None:
    context, warning = detect_git_context(tmp_path, git_available=False)

    assert context.is_repository is False
    assert warning == "Git metadata unavailable because Git was not found."


def test_git_context_degrades_when_git_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", workspace.GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(workspace, "_run_small_git_command", time_out)

    context, warning = detect_git_context(tmp_path, git_available=True)

    assert context.is_repository is False
    assert warning == "Git metadata detection failed: TimeoutExpired."
