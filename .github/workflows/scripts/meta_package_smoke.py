"""Smoke-test the installed `logfire` meta-package and its dependencies."""

from importlib import metadata
from pathlib import Path


def main() -> None:
    """Verify the meta-package installs the matching SDK and standalone CLI."""
    import logfire

    assert logfire.VERSION == metadata.version('logfire')
    assert metadata.version('logfire-cli')

    console_scripts = {
        entry_point.name: entry_point.value for entry_point in metadata.entry_points(group='console_scripts')
    }
    assert console_scripts['logfire'] == 'logfire_cli:main'

    meta_files = metadata.files('logfire')
    assert meta_files is not None
    assert not any(str(path).startswith(('_logfire_sdk/', 'logfire/')) for path in meta_files)
    assert any(str(path).endswith('.dist-info/licenses/LICENSE') for path in meta_files)

    sdk_files = metadata.files('logfire-sdk')
    assert sdk_files is not None
    assert Path('_logfire_sdk/logfire/__init__.py') in sdk_files


if __name__ == '__main__':
    main()
