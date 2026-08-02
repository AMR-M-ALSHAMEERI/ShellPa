"""Privacy-minimal update checks and installation guidance."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version
from rich.console import Console

from . import __version__
from .identity import MICRO_MARK

PYPI_PROJECT_URL = "https://pypi.org/project/shellpa/"
PYPI_METADATA_URL = "https://pypi.org/pypi/shellpa/json"


class UpdateState(str, Enum):
    AVAILABLE = "available"
    CURRENT = "current"
    AHEAD = "ahead"
    FAILED = "failed"


class InstallKind(str, Enum):
    PIPX = "pipx"
    PIP = "pip"
    EDITABLE = "editable"


@dataclass(frozen=True)
class UpdateResult:
    state: UpdateState
    installed_version: str
    latest_version: str | None = None
    detail: str | None = None


def get_update_cache_path() -> Path:
    return Path.home() / ".shellpa" / "update.json"


def _stable_versions(payload: dict[str, Any]) -> list[Version]:
    versions: list[Version] = []
    releases = payload.get("releases")
    if isinstance(releases, dict):
        for raw_version, files in releases.items():
            try:
                version = Version(str(raw_version))
            except InvalidVersion:
                continue
            if version.is_prerelease or version.is_devrelease:
                continue
            if not isinstance(files, list) or not files:
                continue
            if all(
                isinstance(item, dict) and item.get("yanked") is True for item in files
            ):
                continue
            versions.append(version)
    if versions:
        return versions

    info = payload.get("info")
    if isinstance(info, dict) and info.get("yanked") is not True:
        try:
            version = Version(str(info.get("version", "")))
        except InvalidVersion:
            return []
        if not version.is_prerelease and not version.is_devrelease:
            versions.append(version)
    return versions


def fetch_latest_stable_version(*, timeout: float = 4.0) -> str:
    """Read public ShellPa release metadata without sending local configuration."""
    request = Request(
        PYPI_METADATA_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": f"ShellPa/{__version__} update-check",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("PyPI returned an unexpected response.")
    versions = _stable_versions(payload)
    if not versions:
        raise ValueError("PyPI did not report a stable ShellPa release.")
    return str(max(versions))


def _write_update_cache(latest_version: str, path: Path | None = None) -> None:
    cache_path = path or get_update_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "latest_version": latest_version,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=cache_path.parent,
        prefix=f".{cache_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, cache_path)


def _read_update_cache(path: Path | None = None) -> dict[str, str] | None:
    cache_path = path or get_update_cache_path()
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    checked_at = payload.get("checked_at")
    latest_version = payload.get("latest_version")
    if not isinstance(checked_at, str) or not isinstance(latest_version, str):
        return None
    return {"checked_at": checked_at, "latest_version": latest_version}


def weekly_check_due(
    *,
    cache_path: Path | None = None,
    now: datetime | None = None,
) -> bool:
    cached = _read_update_cache(cache_path)
    if cached is None:
        return True
    try:
        checked_at = datetime.fromisoformat(cached["checked_at"])
    except ValueError:
        return True
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    return current_time - checked_at >= timedelta(days=7)


def start_weekly_update_check(
    preference: str,
    *,
    cache_path: Path | None = None,
) -> threading.Thread | None:
    """Start an opt-in cache refresh without delaying terminal startup."""
    if preference != "weekly" or not weekly_check_due(cache_path=cache_path):
        return None

    def refresh() -> None:
        check_for_update(cache_path=cache_path)

    worker = threading.Thread(
        target=refresh,
        name="shellpa-update-check",
        daemon=True,
    )
    worker.start()
    return worker


def cached_available_version(
    preference: str,
    *,
    cache_path: Path | None = None,
) -> str | None:
    if preference != "weekly":
        return None
    cached = _read_update_cache(cache_path)
    if cached is None:
        return None
    try:
        installed = Version(__version__)
        latest = Version(cached["latest_version"])
    except InvalidVersion:
        return None
    if latest > installed and not latest.is_prerelease and not latest.is_devrelease:
        return str(latest)
    return None


def display_cached_update_notice(console: Console, preference: str) -> None:
    latest = cached_available_version(preference)
    if latest is not None:
        console.print(
            f"[cyan]{MICRO_MARK} ShellPa {latest} is available · Run /update[/cyan]"
        )


def check_for_update(*, cache_path: Path | None = None) -> UpdateResult:
    try:
        installed = Version(__version__)
        latest_text = fetch_latest_stable_version()
        latest = Version(latest_text)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
        InvalidVersion,
    ) as exc:
        return UpdateResult(UpdateState.FAILED, __version__, detail=str(exc))
    try:
        _write_update_cache(latest_text, cache_path)
    except OSError:
        # A read-only home directory must not turn a successful public check into
        # an apparent network failure.
        pass
    if latest > installed:
        state = UpdateState.AVAILABLE
    elif latest == installed:
        state = UpdateState.CURRENT
    else:
        state = UpdateState.AHEAD
    return UpdateResult(state, str(installed), str(latest))


def _is_editable_install() -> bool:
    try:
        direct_url = metadata.distribution("shellpa").read_text("direct_url.json")
        if not direct_url:
            return False
        payload = json.loads(direct_url)
        return bool(payload.get("dir_info", {}).get("editable"))
    except (metadata.PackageNotFoundError, json.JSONDecodeError, AttributeError):
        return False


def detect_install_kind() -> InstallKind:
    if _is_editable_install():
        return InstallKind.EDITABLE
    if (Path(sys.prefix) / "pipx_metadata.json").is_file():
        return InstallKind.PIPX
    return InstallKind.PIP


def upgrade_command(kind: InstallKind | None = None) -> str | None:
    install_kind = kind or detect_install_kind()
    if install_kind is InstallKind.EDITABLE:
        return None
    arguments = (
        ["pipx", "upgrade", "shellpa"]
        if install_kind is InstallKind.PIPX
        else [sys.executable, "-m", "pip", "install", "--upgrade", "shellpa"]
    )
    return (
        subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)
    )


def display_guided_update(console: Console) -> UpdateResult:
    """Check PyPI and provide an explicit, user-run upgrade command."""
    console.print(
        f"[bold cyan]{MICRO_MARK} Checking the official PyPI release…[/bold cyan]"
    )
    result = check_for_update()
    if result.state is UpdateState.FAILED:
        console.print(
            f"[yellow]{MICRO_MARK} Update check unavailable.[/yellow] "
            "Your installation was not changed."
        )
        if result.detail:
            console.print(f"[dim]{result.detail}[/dim]")
        return result
    if result.state is UpdateState.CURRENT:
        console.print(
            f"[green]{MICRO_MARK} ShellPa {result.installed_version} is current.[/green]"
        )
        return result
    if result.state is UpdateState.AHEAD:
        console.print(
            f"[cyan]{MICRO_MARK} This build ({result.installed_version}) is ahead of "
            f"the latest stable PyPI release ({result.latest_version}).[/cyan]"
        )
        return result

    console.print(
        f"[bold cyan]{MICRO_MARK} ShellPa {result.latest_version} is available.[/bold cyan]"
    )
    command = upgrade_command()
    if command is None:
        console.print(
            "[yellow]This is an editable development installation. Update its source "
            "branch and dependencies instead of replacing it with the PyPI package.[/yellow]"
        )
    else:
        console.print("Run this command after leaving ShellPa:")
        console.print(f"[bold]{command}[/bold]")
        console.print(
            "[dim]ShellPa will not modify the environment while it is running.[/dim]"
        )
    return result
