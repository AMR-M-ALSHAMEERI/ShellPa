import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

import shellpa.updater as updater


def test_stable_versions_exclude_prereleases_and_fully_yanked_releases() -> None:
    payload = {
        "releases": {
            "0.4.0": [{"yanked": False}],
            "0.5.0rc1": [{"yanked": False}],
            "0.6.0": [{"yanked": True}],
            "0.7.0": [],
        }
    }

    assert [str(version) for version in updater._stable_versions(payload)] == ["0.4.0"]


def test_check_for_update_writes_only_public_version_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "update.json"
    monkeypatch.setattr(updater, "__version__", "0.3.1")
    monkeypatch.setattr(updater, "fetch_latest_stable_version", lambda: "0.4.0")

    result = updater.check_for_update(cache_path=cache_path)

    assert result.state is updater.UpdateState.AVAILABLE
    assert result.latest_version == "0.4.0"
    assert set(json.loads(cache_path.read_text(encoding="utf-8"))) == {
        "checked_at",
        "latest_version",
    }


def test_check_for_update_reports_network_failure_without_raising(monkeypatch) -> None:
    def fail() -> str:
        raise TimeoutError("controlled timeout")

    monkeypatch.setattr(updater, "fetch_latest_stable_version", fail)

    result = updater.check_for_update()

    assert result.state is updater.UpdateState.FAILED
    assert "controlled timeout" in (result.detail or "")


def test_upgrade_command_respects_installation_kind(monkeypatch) -> None:
    assert updater.upgrade_command(updater.InstallKind.PIPX) == "pipx upgrade shellpa"
    assert updater.upgrade_command(updater.InstallKind.EDITABLE) is None

    monkeypatch.setattr(updater.sys, "executable", "C:\\Python\\python.exe")
    command = updater.upgrade_command(updater.InstallKind.PIP)
    assert command is not None
    assert "python.exe" in command
    assert "-m pip install --upgrade shellpa" in command


def test_guided_update_never_executes_the_upgrade(monkeypatch) -> None:
    console = Console(record=True, width=100)
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda: updater.UpdateResult(
            updater.UpdateState.AVAILABLE,
            "0.3.1",
            "0.4.0",
        ),
    )
    monkeypatch.setattr(
        updater,
        "upgrade_command",
        lambda: "pipx upgrade shellpa",
    )

    result = updater.display_guided_update(console)

    assert result.state is updater.UpdateState.AVAILABLE
    output = console.export_text()
    assert "pipx upgrade shellpa" in output
    assert "will not modify" in output


def test_weekly_check_is_due_only_after_seven_days(tmp_path: Path) -> None:
    cache_path = tmp_path / "update.json"
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    cache_path.write_text(
        json.dumps(
            {
                "checked_at": (now - timedelta(days=6)).isoformat(),
                "latest_version": "0.4.0",
            }
        ),
        encoding="utf-8",
    )
    assert updater.weekly_check_due(cache_path=cache_path, now=now) is False

    cache_path.write_text(
        json.dumps(
            {
                "checked_at": (now - timedelta(days=7)).isoformat(),
                "latest_version": "0.4.0",
            }
        ),
        encoding="utf-8",
    )
    assert updater.weekly_check_due(cache_path=cache_path, now=now) is True


def test_weekly_check_requires_opt_in_and_runs_in_background(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[Path | None] = []
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda *, cache_path=None: calls.append(cache_path),
    )
    cache_path = tmp_path / "missing.json"

    assert updater.start_weekly_update_check("manual", cache_path=cache_path) is None
    worker = updater.start_weekly_update_check("weekly", cache_path=cache_path)

    assert worker is not None
    worker.join(timeout=1)
    assert calls == [cache_path]
