"""Privacy-conscious, read-only workspace metadata detection."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping
from pathlib import Path

from .models import (
    GitContext,
    GitHeadState,
    ProjectType,
    PythonEnvironmentContext,
    PythonEnvironmentKind,
    WorkspaceBoundarySource,
    WorkspaceContext,
)

GIT_TIMEOUT_SECONDS = 2.0
MAX_GIT_STATUS_BYTES = 64_000
MAX_GIT_STATUS_ENTRIES = 1_000
MAX_PROVIDER_GIT_LABEL_CHARS = 80

PROJECT_MARKERS: dict[str, ProjectType] = {
    "pyproject.toml": ProjectType.PYTHON,
    "requirements.txt": ProjectType.PYTHON,
    "setup.py": ProjectType.PYTHON,
    "setup.cfg": ProjectType.PYTHON,
    "package.json": ProjectType.NODE,
    "package-lock.json": ProjectType.NODE,
    "pnpm-lock.yaml": ProjectType.NODE,
    "yarn.lock": ProjectType.NODE,
    "bun.lock": ProjectType.NODE,
    "bun.lockb": ProjectType.NODE,
    "Dockerfile": ProjectType.DOCKER,
    "compose.yml": ProjectType.DOCKER,
    "compose.yaml": ProjectType.DOCKER,
    "Cargo.toml": ProjectType.RUST,
    "go.mod": ProjectType.GO,
    "pom.xml": ProjectType.MAVEN,
    "build.gradle": ProjectType.GRADLE,
    "build.gradle.kts": ProjectType.GRADLE,
    "settings.gradle": ProjectType.GRADLE,
    "settings.gradle.kts": ProjectType.GRADLE,
}

KNOWN_TOOLS: dict[str, tuple[str, ...]] = {
    "git": ("git",),
    "python": ("python", "python3", "py"),
    "pip": ("pip", "pip3"),
    "uv": ("uv",),
    "poetry": ("poetry",),
    "pipenv": ("pipenv",),
    "node": ("node",),
    "npm": ("npm",),
    "pnpm": ("pnpm",),
    "yarn": ("yarn",),
    "bun": ("bun",),
    "docker": ("docker",),
    "cargo": ("cargo",),
    "go": ("go",),
    "dotnet": ("dotnet",),
    "java": ("java",),
    "maven": ("mvn",),
    "gradle": ("gradle",),
}


def _marker_exists(directory: Path, marker: str) -> bool:
    """Check one allowlisted marker without reading its contents."""
    try:
        return (directory / marker).exists()
    except OSError:
        return False


def _parents_including(path: Path) -> tuple[Path, ...]:
    return (path, *path.parents)


def resolve_workspace_boundary(
    current_directory: Path,
) -> tuple[Path, WorkspaceBoundarySource]:
    """Resolve a stable boundary, preferring the enclosing Git repository."""
    current = current_directory.resolve()
    nearest_project_root: Path | None = None

    for candidate in _parents_including(current):
        if _marker_exists(candidate, ".git"):
            return candidate, WorkspaceBoundarySource.GIT
        if nearest_project_root is None and any(
            _marker_exists(candidate, marker) for marker in PROJECT_MARKERS
        ):
            nearest_project_root = candidate

    if nearest_project_root is not None:
        return nearest_project_root, WorkspaceBoundarySource.PROJECT_MARKER
    return current, WorkspaceBoundarySource.CURRENT_DIRECTORY


def _detect_markers(root: Path) -> list[str]:
    return sorted(marker for marker in PROJECT_MARKERS if _marker_exists(root, marker))


def _detect_project_types(markers: list[str]) -> list[ProjectType]:
    detected = {PROJECT_MARKERS[marker] for marker in markers}
    return sorted(detected, key=lambda project_type: project_type.value)


def detect_available_tools() -> list[str]:
    """Find known executables without launching them."""
    available = [
        label
        for label, executable_names in KNOWN_TOOLS.items()
        if any(shutil.which(executable) is not None for executable in executable_names)
    ]
    return sorted(available)


def detect_python_environment(
    environment: Mapping[str, str] | None = None,
    *,
    prefix: str | None = None,
    base_prefix: str | None = None,
) -> PythonEnvironmentContext:
    """Identify an active environment from names and interpreter metadata only."""
    active_environment = os.environ if environment is None else environment
    effective_prefix = sys.prefix if prefix is None else prefix
    effective_base_prefix = sys.base_prefix if base_prefix is None else base_prefix

    if active_environment.get("CONDA_PREFIX"):
        kind = PythonEnvironmentKind.CONDA
    elif active_environment.get("PIPENV_ACTIVE"):
        kind = PythonEnvironmentKind.PIPENV
    elif active_environment.get("POETRY_ACTIVE"):
        kind = PythonEnvironmentKind.POETRY
    elif active_environment.get("VIRTUAL_ENV") or (
        effective_prefix != effective_base_prefix
    ):
        kind = PythonEnvironmentKind.VENV
    else:
        return PythonEnvironmentContext()
    return PythonEnvironmentContext(active=True, kind=kind)


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _run_small_git_command(root: Path, *arguments: str) -> subprocess.CompletedProcess:
    """Run a Git command whose output is intrinsically small."""
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
        env=_git_environment(),
    )


def _parse_porcelain_status(
    output: bytes,
    *,
    truncated: bool,
) -> tuple[int, int, bool]:
    """Count status records without retaining their filenames."""
    tracked = 0
    untracked = 0
    records = output.split(b"\0")
    index = 0

    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 3:
            continue
        status = record[:2]
        if status == b"??":
            untracked += 1
        elif status != b"!!":
            tracked += 1
        if b"R" in status or b"C" in status:
            index += 1
        if tracked + untracked >= MAX_GIT_STATUS_ENTRIES:
            truncated = True
            break

    return tracked, untracked, truncated


def _read_bounded_git_status(root: Path) -> tuple[int, int, bool]:
    """Stream bounded porcelain status and discard all filename data."""
    process = subprocess.Popen(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=dirty",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
    )
    if process.stdout is None:
        raise RuntimeError("Git status output was unavailable.")
    status_output = process.stdout

    output = bytearray()
    truncated = [False]

    def read_output() -> None:
        while True:
            chunk = status_output.read(min(4096, MAX_GIT_STATUS_BYTES - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if (
                len(output) >= MAX_GIT_STATUS_BYTES
                or output.count(b"\0") >= MAX_GIT_STATUS_ENTRIES
            ):
                truncated[0] = True
                process.terminate()
                break

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    reader.join(timeout=GIT_TIMEOUT_SECONDS)
    if reader.is_alive():
        truncated[0] = True
        process.kill()
        reader.join(timeout=1.0)

    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        truncated[0] = True
        process.kill()
        process.wait(timeout=1.0)
    status_output.close()

    return _parse_porcelain_status(bytes(output), truncated=truncated[0])


def detect_git_context(
    root: Path, *, git_available: bool
) -> tuple[GitContext, str | None]:
    """Collect bounded, read-only Git facts or return a safe warning."""
    if not git_available:
        return GitContext(), "Git metadata unavailable because Git was not found."

    try:
        inside = _run_small_git_command(root, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
            return GitContext(), None

        branch_result = _run_small_git_command(
            root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
        )
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            branch = branch_result.stdout.strip()
            head_result = _run_small_git_command(root, "rev-parse", "--verify", "HEAD")
            head_state = (
                GitHeadState.BRANCH
                if head_result.returncode == 0
                else GitHeadState.UNBORN
            )
        else:
            branch = None
            head_result = _run_small_git_command(root, "rev-parse", "--verify", "HEAD")
            head_state = (
                GitHeadState.DETACHED
                if head_result.returncode == 0
                else GitHeadState.UNBORN
            )

        tracked, untracked, truncated = _read_bounded_git_status(root)
        return (
            GitContext(
                is_repository=True,
                branch=branch,
                head_state=head_state,
                has_tracked_changes=tracked > 0,
                has_untracked_files=untracked > 0,
                tracked_change_count=tracked,
                untracked_file_count=untracked,
                status_truncated=truncated,
            ),
            None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GitContext(), f"Git metadata detection failed: {type(exc).__name__}."


def detect_workspace(current_directory: Path | None = None) -> WorkspaceContext:
    """Build bounded workspace metadata without reading project file contents."""
    current = (current_directory or Path.cwd()).resolve()
    root, boundary_source = resolve_workspace_boundary(current)
    markers = _detect_markers(root)
    available_tools = detect_available_tools()
    git, git_warning = detect_git_context(
        root,
        git_available="git" in available_tools,
    )
    warnings = [git_warning] if git_warning is not None else []
    return WorkspaceContext(
        root=root,
        current_directory=current,
        boundary_source=boundary_source,
        project_types=_detect_project_types(markers),
        markers=markers,
        available_tools=available_tools,
        git=git,
        python_environment=detect_python_environment(),
        warnings=warnings,
    )


def format_provider_workspace_summary(context: WorkspaceContext) -> str:
    """Return only bounded, non-secret facts suitable for an AI prompt."""
    project_types = (
        ", ".join(project_type.value for project_type in context.project_types)
        if context.project_types
        else "unclassified"
    )
    markers = ", ".join(context.markers) if context.markers else "none"
    lines = [
        f"Workspace boundary: {context.boundary_source.value}",
        f"Project types: {project_types}",
        f"Markers: {markers}",
    ]
    if context.available_tools:
        lines.append(f"Available tools: {', '.join(context.available_tools)}")
    if context.git.is_repository:
        branch = context.git.branch or context.git.head_state.value
        branch = " ".join(branch.split())
        branch = branch.replace("<", "\\u003c").replace(">", "\\u003e")
        branch = branch[:MAX_PROVIDER_GIT_LABEL_CHARS]
        lines.append(f"Git: {branch}")
        lines.append(
            "Git changes: "
            f"{context.git.tracked_change_count} tracked, "
            f"{context.git.untracked_file_count} untracked"
            + (" (bounded)" if context.git.status_truncated else "")
        )
    if context.python_environment.active and context.python_environment.kind:
        lines.append(
            f"Python environment: {context.python_environment.kind.value} (active)"
        )
    if context.warnings:
        lines.append(f"Detection warnings: {len(context.warnings)}")
    return "\n".join(lines)
