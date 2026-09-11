"""Verify the installed ownership and entry points before and after v6 upgrade."""

import sys
from importlib import metadata
from pathlib import Path


def distribution_version(name: str) -> str | None:
    """Return an installed distribution's version, or `None` when absent."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def console_script(name: str) -> str | None:
    """Return a console script's target from the active environment."""
    scripts = {entry_point.name: entry_point.value for entry_point in metadata.entry_points(group='console_scripts')}
    return scripts.get(name)


def assert_v5(expected_major: str) -> None:
    """Check the monolithic v5 distribution before the upgrade."""
    import logfire

    assert logfire.VERSION.startswith(f'{expected_major}.')
    assert distribution_version('logfire') == logfire.VERSION
    assert distribution_version('logfire-sdk') is None
    assert distribution_version('logfire-cli') is None
    assert console_script('logfire') == 'logfire.cli:main'


def assert_v6(expected_major: str) -> None:
    """Check the split distributions and file ownership after the upgrade."""
    import logfire

    assert logfire.VERSION.startswith(f'{expected_major}.')
    assert distribution_version('logfire') == logfire.VERSION
    assert distribution_version('logfire-sdk') == logfire.VERSION
    assert distribution_version('logfire-cli') is not None
    assert console_script('logfire') == 'logfire_cli:main'

    meta_files = metadata.files('logfire')
    assert meta_files is not None
    assert not any(str(path).startswith(('_logfire_sdk/', 'logfire/')) for path in meta_files)

    sdk_files = metadata.files('logfire-sdk')
    assert sdk_files is not None
    assert Path('_logfire_sdk/logfire/__init__.py') in sdk_files

    logfire.configure(send_to_logfire=False)
    with logfire.span('v5 to v6 upgrade works'):
        logfire.info('imported from logfire-sdk')
    assert logfire.force_flush()
    assert logfire.shutdown()


def main() -> None:
    """Run the assertions for the expected major version."""
    expected_major = sys.argv[1]
    if expected_major == '5':
        assert_v5(expected_major)
    elif expected_major == '6':
        assert_v6(expected_major)
    else:
        raise AssertionError(f'Unsupported upgrade-test major version: {expected_major}')


if __name__ == '__main__':
    main()
