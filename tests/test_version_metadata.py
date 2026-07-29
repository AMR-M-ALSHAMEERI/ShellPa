import re
from pathlib import Path

from shellpa import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_and_package_versions_match() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(
        r'(?m)^version\s*=\s*"(?P<version>[^"]+)"\s*$',
        pyproject,
    )

    assert match is not None
    assert match.group("version") == __version__
