"""Lowering the contract's canonical settings into the SDK's `ModelSettings`, and back for the baseline.

The contract names eleven settings every framework is expected to have a knob for. Seven of them are
fields on `ModelSettings` under the same names, one (`thinking`) is `reasoning.effort`, and three are
not expressible at all -- which is the interesting part, because the whole point of a managed config
is that someone can see what it did. Everything this module cannot lower is named here rather than
dropped, so `apply_settings` can report it under the user's `OnUnmatched` policy.

Which of the seven a request actually *sends* depends on the model behind it, so `supported_settings`
takes the resolved model, and its answer is used both when a published value is applied and when the
code baseline is published: a setting the editor is shown as the code's is then one that an override
for it would really reach.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from agents.model_settings import ModelSettings
from agents.models.interface import Model
from agents.models.openai_responses import OpenAIResponsesModel
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort

from .. import canonical_settings

SETTING_FIELDS: Mapping[str, str] = {
    'max_tokens': 'max_tokens',
    'temperature': 'temperature',
    'top_p': 'top_p',
    'presence_penalty': 'presence_penalty',
    'frequency_penalty': 'frequency_penalty',
    'parallel_tool_calls': 'parallel_tool_calls',
    'thinking': 'reasoning',
}
"""Canonical setting -> the `ModelSettings` field it lowers into.

The four canonical settings missing from this table are missing from `ModelSettings` too. `top_k`,
`seed`, and `stop_sequences` reach a provider only through `extra_args`, which for the Responses API
-- the SDK's own default -- is not "sent and ignored" but a `TypeError` out of the OpenAI client's
own signature, raised before a request is built. Forwarding one would trade a setting that does
nothing for an agent that cannot make a request at all. `timeout` is not a knob this SDK offers
either: `ModelSettings` carried no such field before openai-agents 0.22, and where it does carry one
the runner reads it off the settings *before* a model wrapper is handed them, so a value applied here
would be the one setting Logfire showed as applied that never was.
"""

_UNSENT_BY_RESPONSES = ('presence_penalty', 'frequency_penalty')
"""Fields the Responses model has no request parameter for, so it silently sends neither.

`ModelSettings` carries both because the Chat Completions and LiteLLM models do send them. Which of
those three is behind a request is only knowable once the model is resolved, so `supported` is
computed per request instead of once.
"""

_THINKING_EFFORTS: Mapping[bool, ReasoningEffort] = {False: 'none', True: 'medium'}
"""What the contract's boolean `thinking` means to an SDK that only speaks reasoning effort.

`False` is unambiguous: `'none'` is how every OpenAI-shaped model is told not to reason. `True` only
says "reason", so it is lowered to the middle of the scale -- the one choice that is neither a
performance surprise nor a cost one. Publish an explicit effort to mean something narrower.
"""


def supported_settings(model: Model) -> frozenset[str]:
    """The canonical settings this adapter can lower into a request the resolved model will send."""
    if isinstance(model, OpenAIResponsesModel):
        return frozenset(SETTING_FIELDS) - frozenset(_UNSENT_BY_RESPONSES)
    return frozenset(SETTING_FIELDS)


def lower_settings(patch: Mapping[str, Any], current: ModelSettings) -> dict[str, Any]:
    """Turn a canonical settings patch into the `ModelSettings` overlay for this request.

    `current` is the request's own settings, and it is here for `reasoning` alone: the contract can
    only say how hard to think, while `Reasoning` also carries `summary` and `context`, which the
    agent set in code and no one published a replacement for. Overlaying the effort onto the object
    already there keeps them; building a fresh `Reasoning` would quietly drop them.
    """
    overlay: dict[str, Any] = {}
    for key, value in patch.items():
        field = SETTING_FIELDS[key]
        if field == 'reasoning':
            effort = _THINKING_EFFORTS[value] if isinstance(value, bool) else value
            reasoning = current.reasoning or Reasoning()
            overlay[field] = reasoning.model_copy(update={'effort': effort})
        else:
            overlay[field] = value
    return overlay


def settings_layer(settings: ModelSettings, *, only: Collection[str] | None = None) -> dict[str, Any]:
    """The managed `ModelSettings` fields `settings` sets, as one layer for `merge_settings`.

    A merge layer in the SDK's vocabulary rather than the contract's, because that is what the merge
    needs: `merge_settings` only has to know which keys a layer set and which layer wins each one, and
    lowering the published layer into these same field names first (`lower_settings`) means nothing
    has to be translated back afterwards -- what comes out of the merge is the overlay to put on the
    request. `only` narrows the layer to the fields a per-run override named explicitly.
    """
    return {
        field: value
        for field in SETTING_FIELDS.values()
        if (only is None or field in only) and (value := getattr(settings, field)) is not None
    }


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
    canonical: dict[str, Any] = {}
    for key, field in SETTING_FIELDS.items():
        if key not in supported:
            continue
        value = getattr(settings, field)
        if value is None:
            continue
        if field == 'reasoning':
            # `'none'` is the SDK's spelling of the contract's `thinking: false`; every other effort
            # is its own word, and one this release has no word for is left to `canonical_settings`.
            effort: Any = value.effort
            if effort is not None:
                canonical[key] = False if effort == 'none' else effort
        else:
            canonical[key] = value
    return canonical_settings(canonical)
