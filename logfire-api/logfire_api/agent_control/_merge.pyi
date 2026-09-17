from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

SettingSource: TypeAlias

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
    sources: dict[str, SettingSource]
    def source(self, key: str) -> SettingSource | None:
        """Which layer set `key`, or `None` if no layer mentioned it."""

def merge_settings(code: Mapping[str, Any] | None = None, published: Mapping[str, Any] | None = None, run_explicit: Mapping[str, Any] | None = None) -> Provenance:
    '''Merge the three settings layers in contract order, keeping a record of who won.

    Each argument is a flat mapping of that layer\'s settings. `code` and `published` are read as
    patches, so a `None` value in them is "this layer does not set that key" and is skipped: neither
    layer has any way to express "explicitly no value", and treating a `None` there as one would let
    a framework that spells its unset settings out as `None` erase the layer under it.

    `run_explicit` is different, and it is the whole reason this function exists: it holds only the
    keys the caller set *at the call site for this run*, so a `None` in it is a deliberate "send no
    value for this key" and clears whatever the layers under it had. An adapter that cannot see which
    keys a run set explicitly -- a hook handed one already-merged settings object -- should pass
    nothing here and document the weaker contract rather than diff its way to a guess.

    Keys outside the contract\'s canonical eleven pass through untouched, so an adapter can merge its
    framework\'s whole settings object rather than splitting the canonical keys out first: a
    provider-specific key only `code` carries simply survives with `\'code\'` provenance.
    '''
