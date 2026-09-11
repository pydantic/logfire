"""Tests for multi-distribution release version updates."""

from collections.abc import Callable
from pathlib import Path

import pytest

from release.versioning import update_meta_version, update_project_version


def test_update_project_version_only_changes_project_version(tmp_path: Path) -> None:
    """Do not rewrite unrelated version-like settings."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[tool.example]\nversion = "unchanged"\n[project]\nversion = "1.0.0"\n')

    update_project_version(pyproject, '2.0.0')

    assert pyproject.read_text() == '[tool.example]\nversion = "unchanged"\n[project]\nversion = "2.0.0"\n'


def test_update_meta_version_updates_base_and_extra_sdk_pins(tmp_path: Path) -> None:
    """Keep every forwarded SDK extra on the meta-package's release version."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text(
        '[project]\n'
        'version = "1.0.0"\n'
        'dependencies = ["logfire-sdk==1.0.0", "logfire-cli>=0.1.2"]\n'
        '[project.optional-dependencies]\n'
        'fastapi = ["logfire-sdk[fastapi]==1.0.0; python_version >= \'3.10\'"]\n'
    )

    update_meta_version(pyproject, '2.0.0')

    assert pyproject.read_text() == (
        '[project]\n'
        'version = "2.0.0"\n'
        'dependencies = ["logfire-sdk==2.0.0", "logfire-cli>=0.1.2"]\n'
        '[project.optional-dependencies]\n'
        'fastapi = ["logfire-sdk[fastapi]==2.0.0; python_version >= \'3.10\'"]\n'
    )


@pytest.mark.parametrize('updater', [update_project_version, update_meta_version])
def test_version_updaters_fail_when_required_metadata_is_missing(
    tmp_path: Path, updater: Callable[[str | Path, str], None]
) -> None:
    """Fail release preparation rather than silently publishing mismatched versions."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nname = "example"\n')

    with pytest.raises(ValueError, match='project version'):
        updater(pyproject, '2.0.0')


def test_update_meta_version_requires_an_sdk_dependency(tmp_path: Path) -> None:
    """Fail rather than release a meta-package detached from the SDK."""
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nversion = "1.0.0"\ndependencies = ["logfire-cli>=0.1.2"]\n')

    with pytest.raises(ValueError, match='exact logfire-sdk dependency'):
        update_meta_version(pyproject, '2.0.0')
    assert 'version = "1.0.0"' in pyproject.read_text()
