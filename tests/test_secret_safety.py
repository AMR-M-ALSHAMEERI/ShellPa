import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TEXT_FILES = [
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "pyproject.toml",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / "src" / "shellpa").glob("*.py")),
]
SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9_-]{20,}\b"),
)


def test_private_configuration_and_plans_are_git_ignored() -> None:
    ignore_rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignore_rules
    assert ".private/" in ignore_rules


def test_public_project_files_contain_no_secret_shaped_values() -> None:
    findings: list[str] = []
    for path in PUBLIC_TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_SHAPES:
            if pattern.search(text):
                findings.append(str(path.relative_to(ROOT)))

    assert findings == []
