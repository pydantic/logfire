from .. import canonical_settings as canonical_settings
from agents.model_settings import ModelSettings
from agents.models.interface import Model
from collections.abc import Collection, Mapping
from openai.types.shared.reasoning_effort import ReasoningEffort as ReasoningEffort
from typing import Any

SETTING_FIELDS: Mapping[str, str]

def supported_settings(model: Model) -> frozenset[str]:
    """The canonical settings this adapter can lower into a request the resolved model will send."""
def lower_settings(patch: Mapping[str, Any], current: ModelSettings) -> dict[str, Any]:
    """Turn a canonical settings patch into the `ModelSettings` overlay for this request.

    `current` is the request's own settings, and it is here for `reasoning` alone: the contract can
    only say how hard to think, while `Reasoning` also carries `summary` and `context`, which the
    agent set in code and no one published a replacement for. Overlaying the effort onto the object
    already there keeps them; building a fresh `Reasoning` would quietly drop them.
    """
def settings_layer(settings: ModelSettings, *, only: Collection[str] | None = None) -> dict[str, Any]:
    """The managed `ModelSettings` fields `settings` sets, as one layer for `merge_settings`.

    A merge layer in the SDK's vocabulary rather than the contract's, because that is what the merge
    needs: `merge_settings` only has to know which keys a layer set and which layer wins each one, and
    lowering the published layer into these same field names first (`lower_settings`) means nothing
    has to be translated back afterwards -- what comes out of the merge is the overlay to put on the
    request. `only` narrows the layer to the fields a per-run override named explicitly.
    """
def baseline_settings(settings: ModelSettings, supported: Collection[str]) -> dict[str, Any]:
    """The agent's own settings as canonical keys, for the baseline the Logfire editor diffs against.

    Only the settings this adapter would also *apply*, on the model the code actually runs on, are
    described. A baseline is what the editor offers overrides from, so listing a setting that would
    then be refused -- `timeout`, the provider-specific fields `ModelSettings` also carries, or a
    penalty on the Responses API, which has no request field for either -- would advertise a knob
    that is not connected to anything.

    The values go through the core's `canonical_settings`, which is what leaves out a value the
    contract cannot hold rather than approximating it: a reasoning effort outside the contract's own
    vocabulary (`'max'`, today) is not published as its nearest neighbour, because the baseline is
    read as what the code does and the neighbour is not it.
    """
