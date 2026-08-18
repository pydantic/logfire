"""Whether this process is allowed to stop and ask a person something.

`logfire --non-interactive` says the caller cannot answer prompts. Prompts that need an
ANSWER then fail with guidance naming the argument that supplies it, instead of blocking.
Prompts that ask for nothing -- "Press Enter to continue" -- are simply skipped.

WHY A FLAG, when the CLI could just notice that reading fails. Because noticing requires
a read that RETURNS, and stdin can be open and silent: a CI runner, a supervisor or an
agent harness that leaves stdin attached to an idle pipe never sends EOF, so `input()`
waits forever. There is no traceback and no output -- the job just hangs. Detecting EOF
cannot cover that case; declaring intent up front can, because nothing has to be read.

The two are complements. EOF handling still covers callers that cannot be changed (a
command copied out of the docs into an agent), and this covers callers that can say so.
"""

from __future__ import annotations

from logfire.exceptions import LogfireConfigError

_non_interactive = False


class NonInteractiveError(LogfireConfigError):
    """A prompt was needed, but `--non-interactive` says nobody can answer it.

    Carries the guidance the user needs rather than a traceback: the CLI catches this and
    prints `message` before exiting non-zero.
    """


def set_non_interactive(value: bool) -> None:
    """Record whether prompts are allowed. Called once, from CLI argument parsing."""
    global _non_interactive
    _non_interactive = value


def is_non_interactive() -> bool:
    """Whether the caller declared that it cannot answer prompts."""
    return _non_interactive


def require_answer(question: str, remedy: str, *more_remedies: str) -> None:
    """Fail instead of prompting, when the caller said it cannot answer.

    At least one remedy is required by the signature: refusing to prompt while offering no
    way forward just moves the dead end, and telling the caller what to pass is the entire
    value of failing here rather than blocking.

    Args:
        question: what would have been asked, in plain terms.
        remedy: a runnable suggestion.
        more_remedies: further suggestions. Each is printed on its own line, so each must
            be individually pasteable -- `--org a|b` is a shell pipeline, not a suggestion.
    """
    if not _non_interactive:
        return
    raise NonInteractiveError(
        '\n'.join(
            [
                question,
                'Cannot prompt because --non-interactive was passed.',
                'Supply it instead with:',
                *(f'  {r}' for r in (remedy, *more_remedies)),
            ]
        )
    )
