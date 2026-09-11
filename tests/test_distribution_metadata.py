"""Contracts for the `logfire` distribution split."""

import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

import logfire

if sys.version_info >= (3, 11):
    from tomllib import loads
else:
    from tomli import loads

ROOT = Path(__file__).parents[1]


def load_pyproject(path: Path) -> dict[str, Any]:
    """Load a `pyproject.toml` for metadata assertions."""
    return loads(path.read_text())


def test_distribution_versions_and_dependencies_stay_in_sync() -> None:
    """Keep the meta-package pinned to the SDK released from the same tag."""
    sdk = load_pyproject(ROOT / 'pyproject.toml')['project']
    meta = load_pyproject(ROOT / 'logfire-meta' / 'pyproject.toml')['project']
    api = load_pyproject(ROOT / 'logfire-api' / 'pyproject.toml')['project']

    assert sdk['name'] == 'logfire-sdk'
    assert meta['name'] == 'logfire'
    assert sdk['version'] == meta['version'] == api['version']
    assert meta['requires-python'] == sdk['requires-python']
    assert meta['authors'] == sdk['authors']
    assert meta['classifiers'] == sdk['classifiers']
    assert meta['urls'] == sdk['urls']
    assert meta['license-files'] == ['LICENSE']

    requirements = [Requirement(item) for item in meta['dependencies']]
    dependencies = {requirement.name: requirement for requirement in requirements}
    assert str(dependencies['logfire-sdk'].specifier) == f'=={sdk["version"]}'
    assert str(dependencies['logfire-cli'].specifier) == '>=0.1.2'


def test_meta_package_forwards_every_sdk_extra() -> None:
    """Preserve `pip install logfire[extra]` across the distribution split."""
    sdk = load_pyproject(ROOT / 'pyproject.toml')['project']
    meta = load_pyproject(ROOT / 'logfire-meta' / 'pyproject.toml')['project']

    assert meta['optional-dependencies'].keys() == sdk['optional-dependencies'].keys()
    for extra, requirements in meta['optional-dependencies'].items():
        assert requirements == [f'logfire-sdk[{extra}]=={sdk["version"]}']


def test_sdk_does_not_own_the_logfire_executable() -> None:
    """Let the compatibility package forward the standalone CLI executable."""
    sdk = load_pyproject(ROOT / 'pyproject.toml')['project']
    meta = load_pyproject(ROOT / 'logfire-meta' / 'pyproject.toml')['project']

    assert 'scripts' not in sdk
    assert meta['scripts'] == {'logfire': 'logfire_cli:main'}


def test_editable_sdk_uses_the_source_tree() -> None:
    """Keep local edits visible without rebuilding the editable installation."""
    assert Path(logfire.__file__).is_relative_to(ROOT)
    installed_files = metadata.files('logfire-sdk')
    assert installed_files is not None
    assert not any(str(path).startswith(('_logfire_sdk/', 'logfire/')) for path in installed_files)
