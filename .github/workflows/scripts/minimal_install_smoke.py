from __future__ import annotations

from importlib import metadata, util


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


def main() -> None:
    """Smoke-test core logfire APIs in a minimal installation."""
    for package in ('pytest', 'pydantic', 'httpx'):
        assert_not_available(package)

    import logfire

    for package in ('pytest', 'pydantic', 'httpx'):
        assert_not_available(package)

    logfire.configure(send_to_logfire=False, console=False)
    logfire.info('minimal install info', answer=42)
    with logfire.span('minimal install span', answer=42):
        logfire.debug('inside minimal install span')

    counter = logfire.metric_counter('minimal_install_counter')
    counter.add(1)
    assert logfire.force_flush()
    assert logfire.shutdown()


if __name__ == '__main__':
    main()
