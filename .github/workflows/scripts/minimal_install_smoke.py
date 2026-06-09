from __future__ import annotations

from collections.abc import Callable
from importlib import import_module, metadata, util


def assert_not_available(package: str) -> None:
    """Assert that a package is neither installed nor importable."""
    if util.find_spec(package) is not None:
        raise AssertionError(f'{package} should not be importable')

    try:
        metadata.version(package)
    except metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError(f'{package} should not be installed')


def assert_import_error(label: str, func: Callable[[], object], expected_message: str) -> None:
    """Assert that an optional feature fails without its extra dependencies."""
    try:
        func()
    except ImportError as exc:
        if expected_message not in str(exc):
            raise AssertionError(f'{label} raised an unexpected error message: {exc}') from exc
    else:
        raise AssertionError(f'{label} should fail without its extra dependencies')


class NotJsonSerializable:
    """A simple object for exercising non-JSON attribute handling."""


def main() -> None:
    """Smoke-test core logfire APIs in a minimal installation."""
    for package in ('pytest', 'pydantic', 'httpx'):
        assert_not_available(package)

    import logfire

    for package in ('pytest', 'pydantic', 'httpx'):
        assert_not_available(package)

    assert_import_error('testing helpers', lambda: import_module('logfire.testing'), "No module named 'pytest'")
    assert_import_error(
        'query client',
        lambda: import_module('logfire.query_client'),
        'httpx is required to use the Logfire query clients',
    )
    assert_import_error(
        'datasets client',
        lambda: import_module('logfire.experimental.api_client'),
        "No module named 'pydantic'",
    )
    assert_import_error(
        'managed variable imports',
        lambda: getattr(import_module('logfire.variables'), 'Variable'),
        'Using managed variables requires the `pydantic` package',
    )
    assert_import_error(
        'managed variable usage',
        lambda: logfire.var('minimal_install_flag', default=False),
        "No module named 'pydantic'",
    )

    for package in ('pytest', 'pydantic', 'httpx'):
        assert_not_available(package)

    logfire.configure(send_to_logfire=False)
    not_json_serializable = NotJsonSerializable()
    logfire.info('minimal install info', answer=42, not_json_serializable=not_json_serializable)
    with logfire.span('minimal install span', answer=42, not_json_serializable=not_json_serializable):
        logfire.debug('inside minimal install span')

    counter = logfire.metric_counter('minimal_install_counter')
    counter.add(1)
    assert logfire.force_flush()
    assert logfire.shutdown()


if __name__ == '__main__':
    main()
