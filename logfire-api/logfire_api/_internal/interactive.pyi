from collections.abc import Callable
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from typing import TypeVar

T = TypeVar('T')

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
def is_non_interactive() -> bool:
    """Whether the caller declared that it cannot answer prompts."""
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
def ask_or_default(ask: Callable[[], T], default: T) -> T:
    '''Run a prompt, falling back to `default` when stdin runs out before an answer does.

    Mirrors accepting a blank Enter keypress: the caller already declared what "no answer"
    means by passing this SAME value as the prompt\'s own `default=`, so an exhausted stdin
    reaches the outcome a person pressing Enter would, rather than an `EOFError` traceback.
    Only for prompts where that default is genuinely safe to assume -- see `ask_required`
    for one that has no safe default to fall back on.
    '''
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
