from logfire.exceptions import LogfireConfigError as LogfireConfigError

class NonInteractiveError(LogfireConfigError):
    """A prompt was needed, but `--non-interactive` says nobody can answer it.

    Carries the guidance the user needs rather than a traceback: the CLI catches this and
    prints `message` before exiting non-zero.
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
