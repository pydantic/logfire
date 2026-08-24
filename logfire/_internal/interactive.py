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
`ask_or_default`/`ask_required` below are the EOF-handling half: they let a prompt whose
stdin genuinely runs dry (rather than merely being non-interactive by declaration) reach
the same outcome, instead of an unhandled `EOFError` traceback.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from logfire.exceptions import LogfireConfigError

T = TypeVar('T')

_non_interactive = False


class NonInteractiveError(LogfireConfigError):
    """A prompt was needed, but nobody could answer it.

    Carries the guidance the user needs rather than a traceback: the CLI catches this and
    prints `message` before exiting non-zero. Raised either because `--non-interactive`
    said so up front (`require_answer`), or because stdin ran out before an answer arrived
    (`ask_required`) -- the same question/remedy structure either way (only the reason
    line differs), since both mean the same thing to whoever reads it.
    """


def set_non_interactive(value: bool) -> None:
    """Record whether prompts are allowed. Called once, from CLI argument parsing."""
    global _non_interactive
    _non_interactive = value


def is_non_interactive() -> bool:
    """Whether the caller declared that it cannot answer prompts."""
    return _non_interactive


def _cannot_answer(question: str, reason: str, remedy: str, more_remedies: tuple[str, ...]) -> NonInteractiveError:
    return NonInteractiveError(
        '\n'.join(
            [
                question,
                reason,
                'Supply it instead with:',
                *(f'  {r}' for r in (remedy, *more_remedies)),
            ]
        )
    )


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
    if _non_interactive:
        raise _cannot_answer(question, 'Cannot prompt because --non-interactive was passed.', remedy, more_remedies)


def ask_or_default(ask: Callable[[], T], default: T) -> T:
    """Run a prompt, falling back to `default` when stdin runs out before an answer does.

    Mirrors accepting a blank Enter keypress: the caller already declared what "no answer"
    means by passing this SAME value as the prompt's own `default=`, so an exhausted stdin
    reaches the outcome a person pressing Enter would, rather than an `EOFError` traceback.
    Only for prompts where that default is genuinely safe to assume -- see `ask_required`
    for one that has no safe default to fall back on.
    """
    try:
        return ask()
    except EOFError:
        return default


def ask_required(ask: Callable[[], T], question: str, remedy: str, *more_remedies: str) -> T:
    """Run a prompt that has no safe default, raising if stdin runs out before an answer does.

    The reactive half of `require_answer`'s proactive check: that covers a caller who
    declared `--non-interactive` up front, this covers one that did not but ran out of
    input anyway -- a command copied out of the docs into an agent, mid-conversation.
    Raises the same `NonInteractiveError` structure `require_answer` would -- question,
    then reason, then remedies -- with a reason line naming stdin instead of the flag,
    since both mean the same thing to whoever reads it: there was no answer, and here is
    how to supply one.
    """
    try:
        return ask()
    except EOFError:
        raise _cannot_answer(
            question, 'Cannot prompt because there is nothing left to read from stdin.', remedy, more_remedies
        ) from None
