from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_package_contents import (
    unsafe_member_reason,
    verify_artifacts,
)


def write_wheel(path: Path, members: list[str]) -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        for member in members:
            archive.writestr(member, "placeholder")


def write_sdist(path: Path, members: list[str]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for member in members:
            payload = b"placeholder"
            info = tarfile.TarInfo(member)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


@pytest.mark.parametrize(
    "member",
    [
        "shellpa/.private/plan.md",
        "shellpa/.env",
        "shellpa/.env.local",
        "shellpa/.shellpa.env",
        "shellpa/venv/pyvenv.cfg",
        "shellpa/__pycache__/module.pyc",
        "shellpa/auth.json",
        "../outside.txt",
    ],
)
def test_unsafe_package_members_are_rejected(member: str) -> None:
    assert unsafe_member_reason(member) is not None


def test_env_example_is_allowed() -> None:
    assert unsafe_member_reason("shellpa/.env.example") is None


def test_safe_wheel_and_sdist_are_verified(tmp_path: Path) -> None:
    wheel = tmp_path / "shellpa-0.3.0-py3-none-any.whl"
    sdist = tmp_path / "shellpa-0.3.0.tar.gz"
    write_wheel(wheel, ["shellpa/__init__.py", "shellpa-0.3.0.dist-info/METADATA"])
    write_sdist(sdist, ["shellpa-0.3.0/src/shellpa/__init__.py"])

    assert verify_artifacts(tmp_path) == [wheel, sdist]


def test_verifier_reports_unsafe_artifact_member(tmp_path: Path) -> None:
    write_wheel(
        tmp_path / "shellpa-0.3.0-py3-none-any.whl",
        ["shellpa/__init__.py", "shellpa/.env"],
    )

    with pytest.raises(ValueError, match=r"shellpa/\.env"):
        verify_artifacts(tmp_path)
