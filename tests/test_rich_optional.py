"""`rich` is an optional dependency: everything except the Python CLI must work without it."""

from __future__ import annotations

import io
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from inline_snapshot import snapshot

import logfire
from logfire import ConsoleOptions
from logfire._internal.auth import UserTokenCollection
from logfire._internal.config import LogfireCredentials
from logfire._internal.maybe_rich import require_rich


@pytest.fixture
def without_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import rich...` raise `ImportError`."""
    for name in ('rich', 'rich.console', 'rich.prompt'):
        monkeypatch.setitem(sys.modules, name, None)


@pytest.mark.usefixtures('without_rich')
def test_console_exporter_without_rich() -> None:
    output = io.StringIO()
    with pytest.warns(UserWarning, match=r"Console `colors='always'` requires the `rich` package"):
        logfire.configure(
            send_to_logfire=False,
            console=ConsoleOptions(output=output, colors='always', include_timestamps=False, verbose=True),
        )

    with logfire.span('outer {x}', x=[1, 2]):
        logfire.warn('inner')
    try:
        raise ValueError('bad')
    except ValueError:
        logfire.exception('failed')

    # No ANSI escape codes, just plain text.
    assert '\x1b[' not in output.getvalue()
    lines = output.getvalue().splitlines()
    assert lines[:9] == snapshot(
        [
            'outer [1, 2]',
            '│ tests/test_rich_optional.py:38',
            '│ x=[',
            '│       1,',
            '│       2,',
            '│   ]',
            '  inner',
            '│ tests/test_rich_optional.py:39 warn',
            'failed',
        ]
    )
    assert '│ ValueError: bad' in lines


@pytest.mark.usefixtures('without_rich')
def test_console_exporter_without_rich_default_colors() -> None:
    output = io.StringIO()
    # No warning: colors weren't explicitly requested.
    logfire.configure(send_to_logfire=False, console=ConsoleOptions(output=output, include_timestamps=False))
    logfire.info('hello')
    assert output.getvalue() == 'hello\n'


@pytest.mark.usefixtures('without_rich')
def test_token_choice_without_rich(multiple_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    token_collection = UserTokenCollection(multiple_credentials)

    with patch('builtins.input', side_effect=['3', 'nope', '2']):
        token = token_collection.get_token(base_url=None)

    assert token.base_url == 'https://logfire-eu.pydantic.dev'
    assert capsys.readouterr().err.count('Please select one of the available options') == 2


@pytest.mark.usefixtures('without_rich')
def test_print_token_summary_without_rich(capsys: pytest.CaptureFixture[str]) -> None:
    credentials = LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://logfire.pydantic.dev/org/my-project',
        logfire_api_url='https://logfire-api.pydantic.dev',
    )
    credentials.print_token_summary()
    assert capsys.readouterr().err == snapshot('Logfire project URL: https://logfire.pydantic.dev/org/my-project\n')


@pytest.mark.usefixtures('without_rich')
def test_require_rich() -> None:
    with pytest.raises(
        ImportError, match=r'^Some feature requires the `rich` package, install it with `pip install rich`\.$'
    ):
        require_rich('Some feature')


def test_import_and_log_without_rich() -> None:
    """In a fresh process with rich unimportable, `import logfire` and console logging work."""
    code = textwrap.dedent(
        """
        import sys

        sys.modules['rich'] = None

        import logfire

        logfire.configure(
            send_to_logfire=False, inspect_arguments=False, console=logfire.ConsoleOptions(include_timestamps=False)
        )
        with logfire.span('hello {name}', name='world'):
            logfire.info('inside')
        assert 'rich' not in logfire.logfire_info().split('[related_packages]')[0]

        try:
            import logfire.cli
        except ImportError as e:
            print(e)
        """
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert result.stdout == snapshot(
        """\
hello world
  inside
The Logfire Python CLI requires the `rich` package, install it with `pip install rich`.
"""
    )
