"""Python entry points used by the standalone Logfire CLI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from rich.console import Console

from .run import collect_instrumentation_context, parse_run, print_otel_summary

__all__ = ('main',)


def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend packages that might be useful."""
    console = Console(file=sys.stderr)
    ctx = collect_instrumentation_context(set(args.ignore))
    if ctx.recommendations:
        print_otel_summary(console=console, recommendations=ctx.recommendations)
        sys.exit(1)
    console.print('No recommended packages found. You are all set!', style='green')  # pragma: no cover


class SplitArgs(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        if isinstance(values, str):  # pragma: no branch
            values = values.split(',')
        namespace_value: list[str] = getattr(namespace, self.dest) or []
        setattr(namespace, self.dest, namespace_value + list(values or []))


def _main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='python -m logfire', description='Python instrumentation helpers for Logfire.'
    )
    parser.set_defaults(func=lambda _: parser.print_help())  # pyright: ignore[reportUnknownLambdaType]
    subparsers = parser.add_subparsers(title='commands', metavar='')

    cmd_inspect = subparsers.add_parser('inspect', help=parse_inspect.__doc__)
    cmd_inspect.set_defaults(func=parse_inspect)
    cmd_inspect.add_argument('--ignore', action=SplitArgs, default=(), help='ignore a package')

    cmd_run = subparsers.add_parser('run', help='Run Python scripts/modules with Logfire instrumentation')
    cmd_run.add_argument('--summary', action=argparse.BooleanOptionalAction, default=True, help='hide the summary box')
    cmd_run.add_argument('--exclude', action=SplitArgs, default=(), help='exclude a package from instrumentation')
    cmd_run.add_argument('-m', '--module', help='Run module as script')
    cmd_run.add_argument(
        'script_and_args', nargs=argparse.REMAINDER, help='Script path and arguments, or module arguments when using -m'
    )
    cmd_run.set_defaults(func=parse_run)

    namespace, unknown_args = parser.parse_known_args(args)
    if namespace.func == parse_run:
        namespace.script_and_args = unknown_args + (namespace.script_and_args or [])
    else:
        namespace = parser.parse_args(args)
    namespace.func(namespace)


def main(args: list[str] | None = None) -> None:
    """Run the Python instrumentation helpers."""
    try:
        _main(args)
    except KeyboardInterrupt:
        sys.stderr.write('User cancelled.\n')
        sys.exit(1)
