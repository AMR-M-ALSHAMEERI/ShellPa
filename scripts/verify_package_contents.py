"""Fail a release build when an artifact contains private or local-only files."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {
    ".private",
    ".shellpa.env",
    ".venv",
    "__pycache__",
    "auth.json",
    "credentials.json",
    "private.key",
    "venv",
}


def artifact_members(path: Path) -> list[str]:
    """Return normalized member names from a supported Python artifact."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, mode="r:gz") as archive:
            return archive.getnames()
    raise ValueError(f"Unsupported package artifact: {path.name}")


def unsafe_member_reason(name: str) -> str | None:
    """Explain why an archive member is unsafe, or return None."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        return "unsafe archive path"

    for part in path.parts:
        lowered = part.lower()
        if lowered in FORBIDDEN_PARTS:
            return f"contains forbidden path component {part!r}"
        if lowered == ".env" or (
            lowered.startswith(".env.") and lowered != ".env.example"
        ):
            return f"contains local environment file {part!r}"
        if lowered.endswith((".pyc", ".pyo")):
            return f"contains Python cache file {part!r}"
    return None


def verify_artifacts(dist_directory: Path) -> list[Path]:
    """Verify every wheel and source archive in a distribution directory."""
    artifacts = sorted(
        [
            *dist_directory.glob("*.whl"),
            *dist_directory.glob("*.tar.gz"),
        ]
    )
    if not artifacts:
        raise ValueError(f"No package artifacts found in {dist_directory}.")

    findings: list[str] = []
    for artifact in artifacts:
        for member in artifact_members(artifact):
            reason = unsafe_member_reason(member)
            if reason is not None:
                findings.append(f"{artifact.name}: {member}: {reason}")

    if findings:
        details = "\n".join(f"  - {finding}" for finding in findings)
        raise ValueError(f"Unsafe package contents detected:\n{details}")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    dist_directory = Path(arguments[0]) if arguments else Path("dist")
    try:
        artifacts = verify_artifacts(dist_directory)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"Package-content verification failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Package contents verified: "
        + ", ".join(artifact.name for artifact in artifacts)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
