from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

OnUnmatched: TypeAlias

def warn_dropped(message: str) -> None:
    """Surface a dropped managed value once per process.

    A drop means Logfire shows one thing and the agent does another, which has to be visible. But the
    config is resolved on every single request, so warning per drop would bury that signal under its
    own repetition. Deduplicating on the message rather than on the field costs nothing in clarity --
    each message names its subject and the offending value -- and still lets a *different*
    unrecognized value surface later, which a per-field guard would swallow. A concurrent first
    request can at worst duplicate the warning, which is not worth a lock.
    """
def reset_warned_messages() -> None:
    """Forget which messages have been warned about. Intended for tests only."""

ApplyIssueReason: TypeAlias

@dataclass(frozen=True)
class ApplyIssue:
    """One published entry that reached nothing, with the path that says which one.

    Returned by the apply helpers, which report nothing themselves: an adapter collects the issues of
    every section it planned and hands them to
    [`AgentControl.report`][logfire.agent_control.AgentControl.report] once. That is what makes the
    return value load-bearing rather than a duplicate of a warning already emitted, and what lets
    `'error'` fail on everything a request got wrong instead of on the first section planned.

    The fields are a path, and only the ones that apply to `reason` are set -- `tool` and `parameter`
    on a parameter patch, `instruction_id` on an instruction entry, `setting` on a settings key -- so
    an adapter never has to parse `message` to learn what an issue was about.
    """
    section: str
    reason: ApplyIssueReason
    message: str
    instruction_id: str | None = ...
    destination: str | None = ...
    toolset: str | None = ...
    tool: str | None = ...
    parameter: str | None = ...
    setting: str | None = ...
    @classmethod
    def dropped_by_provider(cls, setting: str, detail: str) -> ApplyIssue:
        '''One setting the adapter forwarded and the provider, or its own SDK, did not apply.

        The one issue the core cannot find for itself: it is discovered *after* the request, by an
        adapter reading whatever its framework reports -- the Vercel AI SDK\'s `result.warnings`, a
        provider\'s own "unsupported parameter" note. Those shapes differ per SDK and the core knows
        none of them, so it takes the two things every one of them carries: which canonical setting,
        and what the SDK said about it.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        control.report(*(ApplyIssue.dropped_by_provider(\'top_k\', w.detail) for w in result.warnings))
        ```

        Args:
            setting: The canonical settings key that did not reach the model.
            detail: What the provider or SDK said, in its own words, as one clause.
        '''

class UnmatchedConfigError(ValueError):
    '''Raised by `on_unmatched=\'error\'` for everything one request could not apply.

    A `ValueError` so a deployment that was catching one keeps catching this, and a class of its own
    so an adapter can tell a config the deployment asked to fail on from a model or tool failure --
    and translate it into its own framework\'s error type without restating a single message:

    ```python skip-run="true" skip-reason="illustrative-fragment"
    try:
        control.report(*issues)
    except UnmatchedConfigError as exc:
        raise MyFrameworkError(str(exc)) from exc
    ```

    Raised once for a whole request, with every issue\'s message in `str(exc)` and the issues
    themselves on `issues`, so an adapter that reports a kind it has never heard of still reports it
    faithfully.
    '''
    issues: tuple[ApplyIssue, ...]
    def __init__(self, message: str, issues: Sequence[ApplyIssue] = ()) -> None: ...

def report_unmatched(policy: OnUnmatched, message: str) -> None:
    """Apply an `OnUnmatched` policy to one thing an adapter could not apply, as a message.

    Never called from validation, for two reasons. Validation runs inside Logfire's resolution, which
    turns any exception into a fallback to the code-defined agent, so an `'error'` raised there would
    be swallowed and un-manage the whole config instead of stopping the request. And the same
    validation builds the code baseline, where a key this contract has no field for is the agent's
    own provider-specific setting rather than anything anyone published.

    The message is the same under every policy so a warning someone chose to tolerate reads like the
    error they would have gotten by not tolerating it.
    """
def report_issues(policy: OnUnmatched, issues: Sequence[ApplyIssue]) -> None:
    """Apply one `OnUnmatched` policy to every issue a request's planning produced.

    One call for a whole request, which is the point: the apply helpers plan and report nothing, so
    `'error'` raises after every section has been planned, naming all of it, rather than on the first
    entry of the first section -- which used to mean the strictest policy reported the least.

    Raises:
        UnmatchedConfigError: naming every issue, when `policy` is `'error'`.
    """
