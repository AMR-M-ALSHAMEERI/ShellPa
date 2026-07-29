"""Privacy-conscious, read-only workspace metadata detection."""

from __future__ import annotations

from pathlib import Path

from .models import (
    ProjectType,
    WorkspaceBoundarySource,
    WorkspaceContext,
)

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


def detect_workspace(current_directory: Path | None = None) -> WorkspaceContext:
    """Build bounded workspace metadata without reading project file contents."""
    current = (current_directory or Path.cwd()).resolve()
    root, boundary_source = resolve_workspace_boundary(current)
    markers = _detect_markers(root)
    return WorkspaceContext(
        root=root,
        current_directory=current,
        boundary_source=boundary_source,
        project_types=_detect_project_types(markers),
        markers=markers,
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
    if context.warnings:
        lines.append(f"Detection warnings: {len(context.warnings)}")
    return "\n".join(lines)
