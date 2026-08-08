"""Credential-protection scan tests (AIOS-706 section 8).

AIOS-706 section 8 requires credentials to never appear in source code,
version control, or configuration. These tests scan the source tree and
configuration files for hardcoded secret assignments as a regression guard
for the documented credential-protection rule.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Assignment forms: ``key = "literal"``, ``key: "literal"``, ``key="literal"``.
_SECRET_ASSIGNMENT = re.compile(
    r"""(?i)(password|passwd|api[_-]?key|apikey|token|secret|credential|"""
    r"""access[_-]?token|private[_-]?key|authorization)\s*[:=]\s*["'][^"']{6,}["']"""
)
_PRIVATE_KEY_MARKER = re.compile(r"BEGIN (RSA|DSA|EC|OPENSSH|PRIVATE) KEY")


def _scan_targets() -> list[Path]:
    targets: list[Path] = []
    for root in (_PROJECT_ROOT / "src", _PROJECT_ROOT / "config"):
        if root.is_dir():
            targets.extend(p for p in root.rglob("*") if p.is_file())
    for name in ("pyproject.toml", "alembic.ini", ".pre-commit-config.yaml"):
        candidate = _PROJECT_ROOT / name
        if candidate.is_file():
            targets.append(candidate)
    return [p for p in targets if "__pycache__" not in p.parts]


def _ignored(path: Path) -> bool:
    """Skip files that exist solely to hold test values."""
    return "test_" in path.name


class TestNoHardcodedCredentials:
    @pytest.mark.parametrize(
        "path", _scan_targets(), ids=lambda p: str(p.relative_to(_PROJECT_ROOT))
    )
    def test_source_and_config_contain_no_secret_literals(self, path: Path) -> None:
        if _ignored(path) or path.suffix not in {".py", ".toml", ".ini", ".yaml", ".yml"}:
            pytest.skip(f"not a scanned text file: {path}")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            assert not _SECRET_ASSIGNMENT.search(line), (
                f"possible hardcoded secret in "
                f"{path.relative_to(_PROJECT_ROOT)}:{lineno}: {line.strip()}"
            )
            assert not _PRIVATE_KEY_MARKER.search(line), (
                f"private key material in {path.relative_to(_PROJECT_ROOT)}:{lineno}"
            )
