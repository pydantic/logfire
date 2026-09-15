"""Merging code, published, and per-run settings, and remembering which layer won each key.

The contract's precedence is one sentence -- code < published < the values a run passed explicitly --
and three adapters have now implemented it by *diffing* the framework's effective settings against
the agent's own to guess which keys the run asked for. That guess is wrong in exactly the case that
matters: code `temperature=0.2`, published `0.8`, and a run that passes `0.2` explicitly is
indistinguishable from a run that passed nothing, so the published value wins a key the caller
overrode. It cannot be fixed by diffing harder, only by capturing the explicit keys at the boundary
that has them and merging with that knowledge, which is what this module takes in.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

SettingSource: TypeAlias = Literal['code', 'published', 'run']
"""Which layer a merged setting's value came from.

`'code'` is the agent as written, `'published'` is the managed config, and `'run'` is a value the
caller passed explicitly for this one run. They are ordered: a later layer overrides an earlier one,
and nothing else does.
"""


@dataclass(frozen=True)
class Provenance:
    """A merged settings patch, and which layer each key came from.

    The provenance is not decoration. An adapter that has to lower one merged value into a
    provider-specific place -- `providerOptions.openai.parallelToolCalls`, a request timeout composed
    with a caller's own deadline -- needs to know whether the value it is about to write came from the
    run or from the published config, because those two want opposite treatment: a run's value
    replaces what is there, a published one must not stamp over a run's.
    """

    settings: dict[str, Any]
    """The merged patch: every key that has a value, with the winning layer's value."""
    sources: dict[str, SettingSource]
    """The winning layer per key mentioned by any layer.

    A superset of `settings`'s keys: a key here but not there is one a run explicitly *cleared*,
    which an adapter has to be able to tell from a key nobody ever set -- the first means "send no
    value for this", the second means "whatever the framework does by default".
    """

    def source(self, key: str) -> SettingSource | None:
        """Which layer set `key`, or `None` if no layer mentioned it."""
        return self.sources.get(key)


def merge_settings(
    code: Mapping[str, Any] | None = None,
    published: Mapping[str, Any] | None = None,
    run_explicit: Mapping[str, Any] | None = None,
) -> Provenance:
    """Merge the three settings layers in contract order, keeping a record of who won.

    Each argument is a flat mapping of that layer's settings. `code` and `published` are read as
    patches, so a `None` value in them is "this layer does not set that key" and is skipped: neither
    layer has any way to express "explicitly no value", and treating a `None` there as one would let
    a framework that spells its unset settings out as `None` erase the layer under it.

    `run_explicit` is different, and it is the whole reason this function exists: it holds only the
    keys the caller set *at the call site for this run*, so a `None` in it is a deliberate "send no
    value for this key" and clears whatever the layers under it had. An adapter that cannot see which
    keys a run set explicitly -- a hook handed one already-merged settings object -- should pass
    nothing here and document the weaker contract rather than diff its way to a guess.

    Keys outside the contract's canonical eleven pass through untouched, so an adapter can merge its
    framework's whole settings object rather than splitting the canonical keys out first: a
    provider-specific key only `code` carries simply survives with `'code'` provenance.
    """
    settings: dict[str, Any] = {}
    sources: dict[str, SettingSource] = {}
    inherited: tuple[tuple[Mapping[str, Any] | None, SettingSource], ...] = (
        (code, 'code'),
        (published, 'published'),
    )
    for layer, source in inherited:
        for key, value in (layer or {}).items():
            if value is None:
                continue
            settings[key] = value
            sources[key] = source
    for key, value in (run_explicit or {}).items():
        sources[key] = 'run'
        if value is None:
            settings.pop(key, None)
        else:
            settings[key] = value
    return Provenance(settings=settings, sources=sources)
