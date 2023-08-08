from logfire import __version__


def test_logfire_version() -> None:
    assert __version__ is not None
