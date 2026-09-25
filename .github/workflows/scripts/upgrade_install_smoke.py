"""Verify distribution ownership and behavior throughout a v6 upgrade."""

import sqlite3
import sys
from importlib import metadata
from pathlib import Path


def distribution_version(name: str) -> str | None:
    """Return an installed distribution's version, or `None` when absent."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def console_scripts(name: str) -> set[str]:
    """Return every target registered for a console-script name."""
    return {
        entry_point.value for entry_point in metadata.entry_points(group='console_scripts') if entry_point.name == name
    }


def assert_legacy(expected_version: str) -> None:
    """Check the monolithic distribution before the upgrade."""
    import logfire

    assert logfire.VERSION == expected_version
    assert distribution_version('logfire') == expected_version
    assert distribution_version('logfire-sdk') is None
    assert distribution_version('logfire-cli') is None
    assert console_scripts('logfire') == {'logfire.cli:main'}


def assert_sdk(expected_version: str, *, meta: bool, cli: bool) -> None:
    """Check the split SDK's behavior and ownership in the requested state."""
    import logfire

    assert logfire.VERSION == expected_version
    assert distribution_version('logfire') == (expected_version if meta else None)
    assert distribution_version('logfire-sdk') == expected_version
    assert (distribution_version('logfire-cli') is not None) is cli
    assert distribution_version('opentelemetry-instrumentation-sqlite3') is not None
    assert console_scripts('logfire') == ({'logfire_cli:main'} if meta else set())
    assert console_scripts('logfire-cli') == ({'logfire_cli:main'} if cli else set())

    if meta:
        meta_files = metadata.files('logfire')
        assert meta_files is not None
        assert not any(str(path).startswith(('_logfire_sdk/', 'logfire/')) for path in meta_files)

    sdk_distribution = metadata.distribution('logfire-sdk')
    sdk_files = sdk_distribution.files
    assert sdk_files is not None
    assert '_logfire_sdk/logfire/__init__.py' in {path.as_posix() for path in sdk_files}
    package_inits = {
        sdk_distribution.locate_file(path).resolve()
        for path in sdk_files
        if path.as_posix().endswith('logfire/__init__.py')
    }
    assert Path(logfire.__file__).resolve() in package_inits

    logfire.configure(send_to_logfire=False)
    logfire.instrument_sqlite3()
    with logfire.span('split-package lifecycle works'):
        logfire.info('imported from logfire-sdk')
        with sqlite3.connect(':memory:') as connection:
            assert connection.execute('SELECT 1').fetchone() == (1,)
    assert logfire.force_flush()
    assert logfire.shutdown()


def main() -> None:
    """Run the assertions for the expected major version."""
    state, expected_version = sys.argv[1:]
    if state == 'legacy':
        assert_legacy(expected_version)
    elif state == 'split':
        assert_sdk(expected_version, meta=True, cli=True)
    elif state == 'sdk-and-cli':
        assert_sdk(expected_version, meta=False, cli=True)
    elif state == 'sdk-only':
        assert_sdk(expected_version, meta=False, cli=False)
    else:
        raise AssertionError(f'Unsupported upgrade-test state: {state}')


if __name__ == '__main__':
    main()
