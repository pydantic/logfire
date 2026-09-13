from __future__ import annotations

from collections.abc import Callable
from importlib import import_module, metadata, util


def assert_not_available(import_name: str, distribution_name: str | None = None) -> None:
    """Assert that a package is neither installed nor importable."""
    if util.find_spec(import_name) is not None:
        raise AssertionError(f'{import_name} should not be importable')

    try:
        metadata.version(distribution_name or import_name)
    except metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError(f'{distribution_name or import_name} should not be installed')


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
    optional_packages = (
        ('pytest', None),
        ('pydantic', None),
        ('pydantic_handlebars', None),
        ('httpx', None),
        ('openfeature', 'openfeature-sdk'),
    )

    for import_name, distribution_name in optional_packages:
        assert_not_available(import_name, distribution_name)

    import logfire

    for import_name, distribution_name in optional_packages:
        assert_not_available(import_name, distribution_name)

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
        'Using managed variables requires the `pydantic_handlebars` and `pydantic` packages',
    )
    assert_import_error(
        'managed variable usage',
        lambda: logfire.var('minimal_install_flag', default=False),
        'Using managed variables requires the `pydantic_handlebars` and `pydantic` packages',
    )
    assert_import_error(
        'feature flag imports',
        lambda: import_module('logfire.experimental.feature_flags'),
        'Using feature flags requires the `openfeature-sdk`, `pydantic_handlebars`, and `pydantic` packages',
    )
    for import_name, distribution_name in optional_packages:
        assert_not_available(import_name, distribution_name)

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
