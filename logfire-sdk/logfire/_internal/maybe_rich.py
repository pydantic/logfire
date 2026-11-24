"""Terminal output that uses `rich` when it's installed and falls back to plain text when it isn't.

`rich` is an optional dependency of `logfire-sdk`, so every use of it outside the Python CLI goes through this
module. `rich` is imported lazily in each function so that it's only loaded when needed.
"""

from __future__ import annotations

import os
import sys
from textwrap import indent as indent_text
from typing import TYPE_CHECKING, Literal, TextIO

from logfire.exceptions import LogfireConfigError

from .stack_info import warn_at_user_stacklevel

if TYPE_CHECKING:
    from rich.console import Console

__all__ = 'ConsoleColorsValues', 'TextParts', 'ConsoleWriter', 'ask_choice', 'print_project_url', 'require_rich'

ConsoleColorsValues = Literal['auto', 'always', 'never']

# A list of (text, style) pairs that can be passed to rich's `Text.assemble`.
# When printing without colors, just the text is used.
TextParts = list[tuple[str, str]]


class ConsoleWriter:
    """Prints console exporter output, in color with rich if possible, otherwise as plain text."""

    def __init__(self, output: TextIO | None, colors: ConsoleColorsValues) -> None:
        self._output = output
        self._console: Console | None = None
        try:
            from rich.console import Console
        except ImportError:
            if colors == 'always':
                warn_at_user_stacklevel(
                    "Console `colors='always'` requires the `rich` package, output will not be colored. "
                    'Install it with `pip install rich`.',
                    category=UserWarning,
                )
        else:
            if colors == 'auto':
                force_terminal = None
                no_color = None
            else:
                force_terminal = colors == 'always'
                # Rich 15 honors NO_COLOR even with force_terminal=True unless no_color is set explicitly.
                no_color = colors == 'never'
            console = Console(
                color_system='standard' if os.environ.get('PYTEST_VERSION') else 'auto',
                file=output,
                force_terminal=force_terminal,
                highlight=False,
                markup=False,
                no_color=no_color,
                soft_wrap=True,
            )
            # Use plain `print` to `output` instead of rich when we don't need colors
            if console.is_terminal:
                self._console = console

    def print_parts(self, parts: TextParts) -> None:
        """Print styled text parts on one line."""
        if self._console:
            from rich.text import Text

            self._console.print(Text.assemble(*parts))
        else:
            print(''.join(text for text, _style in parts), file=self._output)

    def print_arguments(self, arguments: dict[str, str], indent_str: str) -> None:
        """Print formatted logfire arguments, with Python syntax highlighting when using rich."""
        if self._console:
            self._print_arguments_rich(arguments, indent_str)
        else:
            self._print_arguments_plain(arguments, indent_str)

    def _print_arguments_rich(self, arguments: dict[str, str], indent_str: str) -> None:
        assert self._console is not None
        from rich.syntax import Syntax
        from rich.text import Text

        syntax = Syntax('', 'python', background_color='default')
        for k, value_code in arguments.items():
            # Rich adds a trailing newline when highlighting code without one.
            # Append our own so cropping removes only that generated newline,
            # preserving original trailing newlines and expanded tabs.
            highlighted = syntax.highlight(f'{value_code}\n')
            highlighted.right_crop(1)

            out = Text()
            for i, line in enumerate(highlighted.split('\n', allow_blank=True)):
                if i:
                    out.append('\n')
                out.append(indent_str)
                out.append('│ ', style='blue')
                if i == 0:
                    out.append(f'{k}=', style='blue')
                else:
                    out.append(' ' * (len(k) + 1))
                out.append_text(line)

            self._console.print(out)

    def _print_arguments_plain(self, arguments: dict[str, str], indent_str: str) -> None:
        out: list[str] = []
        for k, value_code in arguments.items():
            # An empty value, e.g. b'', has no lines but still gets its `k=` line
            value_lines = value_code.splitlines() or ['']
            out += [f'{indent_str}│ {k}={value_lines[0]}']
            prefix = f'{indent_str}│ {" " * len(k)} '
            for line in value_lines[1:]:
                out += [f'{prefix}{line}']
        print('\n'.join(out), file=self._output)

    def print_exception(self, exc_type: str, exc_msg: str, exc_tb: str, indent_str: str) -> None:
        """Print an exception's type, message and traceback, with the traceback highlighted when using rich."""
        indented_tb = indent_text(exc_tb, indent_str + '│ ')
        if self._console:
            from rich.console import Group
            from rich.syntax import Syntax
            from rich.text import Text

            barrier = Text(indent_str + '│ ', style='blue', end='')
            exc_type_text = Text(f'{exc_type}: ', end='', style='bold red')
            exc_msg_text = Text(exc_msg)
            tb_syntax = Syntax(indented_tb, 'python', background_color='default')
            self._console.print(Group(barrier, exc_type_text, exc_msg_text), tb_syntax)
        else:
            print(f'{indent_str}│ {exc_type}: {exc_msg}\n{indented_tb}', file=self._output)


ASK_CHOICE_MAX_ATTEMPTS = 5


def ask_choice(prompt: str, count: int) -> int:
    """Ask the user on stderr to pick a number from 1 to `count`.

    Raises:
        LogfireConfigError: If no valid choice is given after `ASK_CHOICE_MAX_ATTEMPTS` attempts.
    """
    choices = [str(i) for i in range(1, count + 1)]
    choices_str = f'[{"/".join(choices)}]'
    invalid_message = 'Please select one of the available options'
    try:
        from rich.console import Console
        from rich.markup import escape
    except ImportError:

        def read_answer() -> str:
            sys.stderr.write(f'{prompt}{choices_str}: ')
            sys.stderr.flush()
            return input()

        def report_invalid() -> None:
            sys.stderr.write(f'{invalid_message}\n')
    else:
        console = Console(file=sys.stderr)

        def read_answer() -> str:
            return console.input(f'{escape(prompt)}[prompt.choices]{escape(choices_str)}[/prompt.choices]: ')

        def report_invalid() -> None:
            console.print(invalid_message, style='prompt.invalid.choice')

    for _ in range(ASK_CHOICE_MAX_ATTEMPTS):
        answer = read_answer().strip()
        if answer in choices:
            return int(answer)
        report_invalid()
    raise LogfireConfigError(f'No valid option was selected after {ASK_CHOICE_MAX_ATTEMPTS} attempts.')


def print_project_url(project_url: str) -> None:
    """Print the Logfire project URL to stderr."""
    try:
        from rich.console import Console
    except ImportError:
        sys.stderr.write(f'Logfire project URL: {project_url}\n')
    else:
        console = Console(stderr=True)
        # Make sure the URL isn't wrapped, so it can be clicked or copied.
        min_width = len(project_url) + 4
        if console.width < min_width:  # pragma: no cover
            console.width = min_width
        console.print(f'[bold]Logfire[/bold] project URL: [cyan]{project_url}[/cyan]')


def require_rich(feature: str) -> None:
    """Raise a helpful `ImportError` if rich isn't installed."""
    try:
        import rich  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError as e:
        raise ImportError(f'{feature} requires the `rich` package, install it with `pip install rich`.') from e
