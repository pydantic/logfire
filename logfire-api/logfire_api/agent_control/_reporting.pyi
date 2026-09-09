from collections.abc import Iterable, Sequence
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
def report_unmatched(policy: OnUnmatched, message: str) -> None:
    """Apply an `OnUnmatched` policy to one published entry that reached nothing.

    Called where the entry would have been applied -- `apply_settings`, `apply_instructions`,
    `apply_tool_definitions` -- and never from validation, for two reasons. Validation runs inside
    Logfire's resolution, which turns any exception into a fallback to the code-defined agent, so an
    `'error'` raised there would be swallowed and un-manage the whole config instead of stopping the
    request. And the same validation builds the code baseline, where a key this contract has no field
    for is the agent's own provider-specific setting rather than anything anyone published.

    The message is the same under every policy so a warning someone chose to tolerate reads like the
    error they would have gotten by not tolerating it.
    """
def reset_warned_messages() -> None:
    """Forget which messages have been warned about. Intended for tests only."""

UnappliedReason: TypeAlias

@dataclass(frozen=True)
class UnappliedEntry:
    """One published entry that reached nothing, with the path that says which one.

    Returned by the apply helpers so an adapter can do more than repeat the message: count them,
    attach them to a span, decide per section, or feed the tool ones back into its own routing. The
    fields are a path, and only the ones that apply to `reason` are set -- `tool` and `parameter` on
    a parameter patch, `instruction_id` on an instruction entry -- so an adapter never has to parse
    `message` to learn what an entry was about.

    The helpers report every entry they return under the caller's `OnUnmatched` policy before
    returning it, so an adapter that only wants the configured behavior can ignore these entirely and
    one that wants both does not get the message twice.
    """
    reason: UnappliedReason
    message: str
    instruction_id: str | None = ...
    toolset: str | None = ...
    tool: str | None = ...
    parameter: str | None = ...

def report_unapplied(policy: OnUnmatched, entries: Iterable[UnappliedEntry]) -> Sequence[UnappliedEntry]:
    """Apply one `OnUnmatched` policy to every entry that reached nothing, and hand them back.

    One call site per helper, so the policy governs *all* of a section's decisions rather than the
    subset that happened to be routed through it: a rename dropped for colliding is as much a gap
    between what Logfire shows and what the agent does as an override naming a tool that is not
    there, and `'ignore'` has to silence both while `'error'` has to fail on both.

    Raises:
        ValueError: on the first entry, when `policy` is `'error'`.
    """
