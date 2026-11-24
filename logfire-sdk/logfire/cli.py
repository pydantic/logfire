from ._internal.maybe_rich import require_rich

require_rich('The Logfire Python CLI')

from ._internal.cli import main  # noqa: E402

__all__ = ('main',)
