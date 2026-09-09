"""Saying out loud that Logfire shows one thing and the agent does another."""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

OnUnmatched: TypeAlias = Literal['ignore', 'warn', 'error']
"""What to do with a published entry that reaches nothing in this deployment.

That is an instruction `id` no block carries (or that only a dynamic block carries), a tool override
whose `name` -- and `toolset`, when it sets one -- matches no tool the agent advertises, and a
`settings` key the contract or the adapter cannot apply. Each is a place where Logfire shows one
thing and the agent does another.

- `'warn'` (the default everywhere) emits a `UserWarning` once per process per message, at the point
  the entry would have been applied.
- `'error'` raises `ValueError` with the same message at that point, failing the request.
- `'ignore'` applies nothing and says nothing.

Warning rather than raising is the default because tool availability is dynamic: one config is
applied across deployments that need not all install the same tools, and an agent can advertise
different tools from one request to the next, so an entry that reaches nothing here may be exactly
right somewhere else. `'error'` is for the deployment that would rather stop than run with part of
its published config silently unapplied.
"""

_warned: set[str] = set()
"""Messages already emitted in this process; see `warn_dropped`."""


def warn_dropped(message: str) -> None:
    """Surface a dropped managed value once per process.

    A drop means Logfire shows one thing and the agent does another, which has to be visible. But the
    config is resolved on every single request, so warning per drop would bury that signal under its
    own repetition. Deduplicating on the message rather than on the field costs nothing in clarity --
    each message names its subject and the offending value -- and still lets a *different*
    unrecognized value surface later, which a per-field guard would swallow. A concurrent first
    request can at worst duplicate the warning, which is not worth a lock.
    """
    if message in _warned:
        return
    _warned.add(message)
    warnings.warn(message)


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
    if policy == 'error':
        raise ValueError(message)
    if policy == 'warn':
        warn_dropped(message)


def reset_warned_messages() -> None:
    """Forget which messages have been warned about. Intended for tests only."""
    _warned.clear()


UnappliedReason: TypeAlias = Literal[
    'unknown-id',
    'dynamic-id',
    'oversized-text',
    'unknown-tool',
    'unknown-parameter',
    'no-patchable-schema',
    'rename-collision',
]
"""Why one published entry did not reach the request, as a stable string an adapter can branch on.

Instructions:

- `'unknown-id'` -- an `id` this request assembles no block under.
- `'dynamic-id'` -- an `id` only a block the framework recomputes per request carries, which cannot
  be replaced or dropped without pinning or removing that computation.
- `'oversized-text'` -- text past the contract's per-request budget, which is refused rather than
  truncated: half a prompt is not a smaller version of the prompt.

Tools:

- `'unknown-tool'` -- a `name` (narrowed by `toolset` when the entry sets one) no advertised tool has.
- `'unknown-parameter'` -- a `parameters` key the tool's schema has no top-level property for.
- `'no-patchable-schema'` -- the tool, or that one property, has no object schema to patch a
  description into at all.
- `'rename-collision'` -- a `new_name` another advertised tool, or a name the adapter reserved,
  already answers to. The rename is dropped and the tool keeps its code-side name; the same entry's
  other patches still apply.

These are the runtime decisions: what a *valid* published value did not reach in *this* deployment,
on *this* request. They are deliberately not the parser's compatibility warnings -- an entry a newer
UI wrote that this release cannot understand -- which are about the value rather than the request,
warn once per process from validation, and never take an `OnUnmatched` policy.
"""


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
    """Why it was not applied; see [`UnappliedReason`][logfire.agent_control.UnappliedReason]."""
    message: str
    """What the policy reports: what was published, and what was not applied."""
    instruction_id: str | None = None
    """The instruction `id` the entry addressed, for the instruction reasons."""
    toolset: str | None = None
    """The toolset the entry named or the tool came from, when either has one."""
    tool: str | None = None
    """The code-side tool name the entry named, for the tool reasons."""
    parameter: str | None = None
    """The parameter the entry patched, for `'unknown-parameter'` and `'no-patchable-schema'`."""


def report_unapplied(policy: OnUnmatched, entries: Iterable[UnappliedEntry]) -> Sequence[UnappliedEntry]:
    """Apply one `OnUnmatched` policy to every entry that reached nothing, and hand them back.

    One call site per helper, so the policy governs *all* of a section's decisions rather than the
    subset that happened to be routed through it: a rename dropped for colliding is as much a gap
    between what Logfire shows and what the agent does as an override naming a tool that is not
    there, and `'ignore'` has to silence both while `'error'` has to fail on both.

    Raises:
        ValueError: on the first entry, when `policy` is `'error'`.
    """
    collected = list(entries)
    for entry in collected:
        report_unmatched(policy, entry.message)
    return collected
