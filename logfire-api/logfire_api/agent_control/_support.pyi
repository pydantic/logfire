from dataclasses import dataclass
from typing import Literal, TypeAlias

Section: TypeAlias

@dataclass(frozen=True)
class Destination:
    """One named sink an adapter can put instruction text into.

    A framework with one prompt has one destination; a framework with several -- a CLI preset and a
    system prompt, a session prefix and a per-turn prefix -- has one per sink, and a published
    addition says which of them it means rather than an index into a list only the adapter can see.

    Declared here and consumed where instructions are applied, so the editor learns the sinks from
    the same value that tells it which sections exist.
    """
    id: str
    default: bool = ...
    accepts_additions: bool = ...

@dataclass(frozen=True)
class AgentSupport:
    """What this adapter can apply, declared once and carried with the baseline.

    An adapter builds one of these and passes it to the apply helpers, which use it to say -- rather
    than silently do nothing about -- a published section or setting this framework cannot lower. The
    Logfire editor reads the same value to grey out what it would be pointless to publish.

    Nothing here is about a model. A published `temperature` a reasoning model refuses, or a
    `presence_penalty` a provider rejects outright, reaches that provider and fails the request
    unless the adapter's own reasoning drops it first: that is the adapter's table to get right, and
    Agent Control carries none of it.
    """
    sections: frozenset[Section]
    destinations: tuple[Destination, ...] = ...
    settings: frozenset[str] = ...
    precedence: Literal['exact', 'inferred', 'code-wins'] = ...
    resolution_unit: Literal['run', 'request', 'session'] = ...
