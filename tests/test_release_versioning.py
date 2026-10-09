"""Tests for multi-distribution release version updates."""

from pathlib import Path

import pytest

from release.versioning import update_project_version


def test_update_project_version_only_changes_project_version(tmp_path: Path) -> None:
    """Do not rewrite unrelated version-like settings."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[tool.example]\nversion = "unchanged"\n[project]\nversion = "1.0.0"\n')

    update_project_version(pyproject, '2.0.0b1')

    assert pyproject.read_text() == '[tool.example]\nversion = "unchanged"\n[project]\nversion = "2.0.0b1"\n'


def test_version_updater_fails_when_required_metadata_is_missing(tmp_path: Path) -> None:
    """Fail release preparation rather than silently publishing mismatched versions."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nname = "example"\n')

    with pytest.raises(ValueError, match='project version'):
        update_project_version(pyproject, '2.0.0')
