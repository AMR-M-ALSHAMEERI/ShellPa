import pytest

import shellpa.os_detect as os_detect


def test_detects_windows_powershell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os_detect.platform, "system", lambda: "Windows")
    monkeypatch.setenv("PSModulePath", "C:\\PowerShell\\Modules")

    result = os_detect.detect_environment()

    assert result["os"] == "Windows"
    assert result["shell"] == "powershell"
    assert result["is_windows"] is True


def test_detects_windows_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os_detect.platform, "system", lambda: "Windows")
    monkeypatch.delenv("PSModulePath", raising=False)
    monkeypatch.setenv("COMSPEC", "C:\\Windows\\System32\\cmd.exe")

    assert os_detect.detect_environment()["shell"] == "cmd"


@pytest.mark.parametrize(
    ("system", "shell_path", "expected_shell"),
    [
        ("Darwin", "/bin/zsh", "zsh"),
        ("Linux", "/bin/bash", "bash"),
        ("Linux", "/usr/bin/fish", "fish"),
    ],
)
def test_detects_posix_shells(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    shell_path: str,
    expected_shell: str,
) -> None:
    monkeypatch.setattr(os_detect.platform, "system", lambda: system)
    monkeypatch.setenv("SHELL", shell_path)

    assert os_detect.detect_environment()["shell"] == expected_shell
