"""Lowering the contract's canonical model settings into ADK's `GenerateContentConfig`, and back.

ADK expresses model settings as a `google.genai` `GenerateContentConfig`, and every backend it
supports -- Gemini, Anthropic, LiteLLM -- reads that object for itself. They do not read the same
fields out of it, which is the whole reason this module has a `Backend` in it: a field ADK lets an
adapter *set* is not a setting the model serving the request will *apply*, and reporting the
difference is the only thing standing between a published value and an agent that quietly ignores it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.genai import types

from .. import to_milliseconds

_FIELDS: dict[str, str] = {
    'max_tokens': 'max_output_tokens',
    'temperature': 'temperature',
    'top_p': 'top_p',
    'top_k': 'top_k',
    'seed': 'seed',
    'presence_penalty': 'presence_penalty',
    'frequency_penalty': 'frequency_penalty',
    'stop_sequences': 'stop_sequences',
}
"""Canonical setting -> `GenerateContentConfig` field, for the settings that are one field each."""

CONFIGURABLE = frozenset({*_FIELDS, 'timeout', 'thinking'})
"""The canonical settings a `GenerateContentConfig` can carry at all, whoever ends up reading it.

`parallel_tool_calls` is deliberately absent: `GenerateContentConfig` has no field for it, and the
one backend that can express it (LiteLLM) takes it as a constructor argument on the model object, so
it is not something a per-request hook can change. It is reported rather than dropped.

Being in this set is necessary and not sufficient -- see `Backend`.
"""


@dataclass(frozen=True)
class Backend:
    """What one family of ADK model classes actually reads out of a `GenerateContentConfig`.

    ADK's request object is Gemini-shaped, and its other backends translate the parts of it they
    understand. Applying a setting the backend does not translate is not a smaller change than
    intended -- it is no change at all, with the Logfire UI showing a value the agent never used, so
    it belongs under `on_unmatched` like any other published value that reached nothing.

    A backend that hands the config straight to a provider has a second reason to leave a setting
    off: one the *provider* refuses is not ignored, it fails the request, which is the one thing a
    published value must never be able to do. Those are recorded here too, against the observed
    behaviour of the API rather than against ADK's source -- see the tests that record it live.
    """

    label: str
    """How to name this backend in a message to whoever published a setting it does not read.

    A noun phrase rather than a bare name, so an unknown backend reads as "the model serving this
    request" rather than as a name nobody would recognize.
    """
    settings: frozenset[str]
    """The canonical settings this backend reads. A subset of `CONFIGURABLE`."""
    thinking_levels: bool
    """Whether `thinking_config.thinking_level` is read, as opposed to `thinking_budget` alone."""


_GEMINI_SETTINGS = CONFIGURABLE - {'presence_penalty', 'frequency_penalty'}
"""What a Gemini model takes, which is everything ADK forwards except the two penalties.

ADK does forward them -- it hands the whole config to `google-genai` -- but the Gemini API answers
`400 Penalty is not enabled for models/<name>`, observed on `gemini-2.5-flash-lite`,
`gemini-2.5-flash`, `gemini-2.5-pro` and `gemini-3.5-flash-lite`. A published setting that fails the
request is worse than one that is ignored, so the two are left off and reported like any other
setting this request's model has no knob for.
"""

_GEMINI = Backend(label='Gemini model', settings=_GEMINI_SETTINGS, thinking_levels=False)
"""A Gemini model from before `thinking_level`, which asks for thinking as a budget."""

_GEMINI_WITH_THINKING_LEVELS = Backend(label='Gemini model', settings=_GEMINI_SETTINGS, thinking_levels=True)
"""A Gemini model that takes `thinking_level`, which from Gemini 3 replaced the zero budget.

The two spellings are mutually exclusive on both sides, and the API says so: Gemini 2.5 answers
`400 Thinking level is not supported for this model`, and Gemini 3.5 refuses `thinking_budget=0`.
An automatic budget (`-1`) is accepted by both, which is why `thinking=True` needs no split.
"""

_GEMINI_GENERATION = re.compile(r'^gemini-(\d+)')
"""The generation in a Gemini model name, when it carries one at all."""

_THINKING_LEVEL_GENERATION = 3
"""The Gemini generation from which `thinking_level` is the way to ask for less thinking."""


def _gemini_backend(model: str) -> Backend:
    """Which of the two Gemini backends serves `model`, by the generation in its name.

    A name with no generation in it -- an alias like `gemini-flash-lite-latest`, or a `Gemma` -- is
    treated as a current one, because the aliases track the newest release (`gemini-flash-lite-latest`
    is a Gemini 3 model today, and refuses a zero budget) and because a name this cannot read is more
    likely to be newer than the last generation this adapter was written against.
    """
    generation = _GEMINI_GENERATION.match(model)
    if generation is not None and int(generation[1]) < _THINKING_LEVEL_GENERATION:
        return _GEMINI
    return _GEMINI_WITH_THINKING_LEVELS


_CLAUDE = Backend(
    label='Claude model',
    # `Claude._build_anthropic_kwargs` reads exactly these. It has no `seed`, no penalties, and no
    # per-request timeout: it reads `http_options` for nothing at all.
    settings=frozenset({'max_tokens', 'temperature', 'top_p', 'top_k', 'stop_sequences', 'thinking'}),
    # A `thinking_budget` becomes Anthropic's disabled/adaptive/enabled thinking, but a
    # `thinking_level` is explicitly refused: ADK warns and drops it, because the four canonical
    # levels do not map onto Anthropic's five efforts. Effort is set through ADK's own
    # `AnthropicGenerateContentConfig`, which is a model-construction choice rather than a
    # per-request field this adapter could reach.
    thinking_levels=False,
)
"""ADK's Anthropic client."""

_LITELLM = Backend(
    label='LiteLLM model',
    # `_get_completion_inputs` maps seven fields into LiteLLM's completion arguments, and
    # `generate_content_async` reads `http_options.timeout` on top of them. `seed` and the whole
    # `thinking_config` are read by neither.
    settings=frozenset(
        {
            'max_tokens',
            'temperature',
            'top_p',
            'top_k',
            'stop_sequences',
            'presence_penalty',
            'frequency_penalty',
            'timeout',
        }
    ),
    thinking_levels=False,
)
"""ADK's LiteLLM client, which is how every provider ADK has no client of its own for is reached."""

UNKNOWN_BACKEND = Backend(label='model', settings=CONFIGURABLE, thinking_levels=True)
"""A `BaseLlm` subclass this adapter has never heard of, which is a deployment's own model class.

Assumed to read the whole request config, because it is written against the same `LlmRequest` ADK's
own clients are and there is nothing else to go on. It is the one case where a published setting can
still go unapplied without a word -- dropped by the model class, out of this adapter's sight.
"""

_BACKENDS: dict[str, Backend] = {
    'google.adk.models.google_llm.Gemini': _GEMINI,
    'google.adk.models.anthropic_llm.Claude': _CLAUDE,
    'google.adk.models.lite_llm.LiteLlm': _LITELLM,
}
"""Which backend serves a model class, keyed by name so no optional provider extra is imported.

`anthropic` and `litellm` are extras a deployment need not have installed, and importing either to
run an `isinstance` check would make this adapter refuse to load in a Gemini-only deployment.
"""


def backend_of(model: BaseLlm) -> Backend:
    """What the model serving a request reads, found through the class it inherits from.

    ADK's own subclasses -- `Gemma` on top of `Gemini`, `Gemma3Ollama` on top of `LiteLlm` -- read
    what their base reads, so the whole MRO is walked rather than the exact class matched.

    The Gemini client is the one that then asks the model's *name* a second question, because it
    forwards the request config untranslated: what reaches the provider is decided by the model
    rather than by the class, and the two Gemini generations disagree about how to ask for thinking.
    """
    for cls in type(model).__mro__:
        backend = _BACKENDS.get(f'{cls.__module__}.{cls.__qualname__}')
        if backend is _GEMINI:
            return _gemini_backend(model.model)
        if backend is not None:
            return backend
    return UNKNOWN_BACKEND


_THINKING_LEVELS: dict[str, types.ThinkingLevel] = {
    'minimal': types.ThinkingLevel.MINIMAL,
    'low': types.ThinkingLevel.LOW,
    'medium': types.ThinkingLevel.MEDIUM,
    'high': types.ThinkingLevel.HIGH,
}
"""Canonical thinking effort -> `ThinkingLevel`. `'xhigh'` has no member and is reported, not rounded."""

_LEVEL_NAMES = {level: name for name, level in _THINKING_LEVELS.items()}

_AUTOMATIC_THINKING_BUDGET = -1
"""`thinking=True`: let the model decide how much to think, which is Gemini's `-1` budget.

The one spelling every backend and every Gemini generation takes, which is why it needs no
per-generation choice the way `thinking=False` does.
"""

_NO_THINKING_BUDGET = 0
"""`thinking=False` on a model that counts thinking in tokens, which is Gemini before 3 and Claude."""

_BUDGET_MEANINGS: dict[int, bool] = {_AUTOMATIC_THINKING_BUDGET: True, _NO_THINKING_BUDGET: False}
"""The budgets the contract can describe, for reading an agent's own config back into a baseline."""


def _thinking_config(thinking: bool | str, backend: Backend) -> types.ThinkingConfig | None:
    """The `ThinkingConfig` for a canonical `thinking` value, or `None` when `backend` cannot express it."""
    if thinking is True:
        return types.ThinkingConfig(thinking_budget=_AUTOMATIC_THINKING_BUDGET)
    if thinking is False:
        # "As little as the model allows" has two spellings and a model takes exactly one of them:
        # Gemini 3 answers `400` to the zero budget its predecessors want, and Gemini 2.5 answers
        # `400` to the minimal level that replaced it.
        return (
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
            if backend.thinking_levels
            else types.ThinkingConfig(thinking_budget=_NO_THINKING_BUDGET)
        )
    if not backend.thinking_levels:
        return None
    level = _THINKING_LEVELS.get(thinking)
    return None if level is None else types.ThinkingConfig(thinking_level=level)


def _unread(name: str, backend: Backend) -> str:
    return (
        f'Managed agent config sets {name!r}, which the {backend.label} serving this request does not read; '
        'that setting is not applied.'
    )


def apply(config: types.GenerateContentConfig, settings: Mapping[str, Any], backend: Backend) -> list[str]:
    """Merge a canonical settings patch into one request's config, in place.

    The config is ADK's per-request copy of the agent's own, so writing to it changes this request
    and nothing else. Only what `backend` reads is written: a setting this request's model would
    ignore is left off the request entirely rather than set where the Logfire UI can see it and the
    model cannot. Returns a message for every setting that went unapplied for either reason -- the
    backend does not read that key, or does not read that value -- for the caller to report under its
    `on_unmatched` policy.
    """
    unapplied: list[str] = []
    for name, field in _FIELDS.items():
        if name not in settings:
            continue
        if name in backend.settings:
            setattr(config, field, settings[name])
        else:
            unapplied.append(_unread(name, backend))
    if (timeout := settings.get('timeout')) is not None:
        if 'timeout' in backend.settings:
            # The contract counts a timeout in seconds, as every SDK's own settings do; the genai
            # client counts it in milliseconds. Everything else here is a rename, so this is the one
            # conversion, and the core owns its rounding so that every adapter converts alike.
            config.http_options = config.http_options or types.HttpOptions()
            config.http_options.timeout = to_milliseconds(timeout)
        else:
            unapplied.append(_unread('timeout', backend))
    if (thinking := settings.get('thinking')) is not None:
        # Replaces rather than merges, including a `thinking_config` an agent's `BuiltInPlanner` put
        # here: a published effort that left the planner's budget in place would be neither value.
        thinking_config = _thinking_config(thinking, backend) if 'thinking' in backend.settings else None
        if thinking_config is None:
            unapplied.append(
                f'Managed agent config sets thinking to {thinking!r}, which the {backend.label} serving this '
                'request has no thinking level for; that setting is not applied.'
            )
        else:
            config.thinking_config = thinking_config
    return unapplied


def describe(config: types.GenerateContentConfig | None, backend: Backend) -> dict[str, Any]:
    """The agent's own settings in the contract's canonical names, for the code baseline.

    Only the canonical keys are described, and only the ones the agent's own model reads. A
    `GenerateContentConfig` also carries provider-specific settings and `http_options.headers`, which
    is where an authorization header lives, and the baseline is published where every member of the
    Logfire project can read it. A setting the agent sets and its backend ignores is left out for a
    different reason: the baseline is what the editor presents as the truth about the code, and a
    value the agent never actually sends is not part of that truth.
    """
    if config is None:
        return {}
    settings: dict[str, Any] = {}
    for name, field in _FIELDS.items():
        if name in backend.settings and (value := getattr(config, field, None)) is not None:
            settings[name] = value
    # `top_k` is the one field whose ADK type is wider than the contract's: genai takes a float, the
    # contract takes an int. A fractional one describes nothing the contract can say, so it is left
    # out rather than rounded into a different agent than the one the code runs.
    if isinstance(top_k := settings.get('top_k'), float):
        settings['top_k'] = int(top_k) if top_k.is_integer() else None
    if 'timeout' in backend.settings and config.http_options is not None and config.http_options.timeout is not None:
        settings['timeout'] = config.http_options.timeout / 1000
    if 'thinking' in backend.settings and (thinking_config := config.thinking_config) is not None:
        if thinking_config.thinking_level is not None:
            settings['thinking'] = _LEVEL_NAMES.get(thinking_config.thinking_level) if backend.thinking_levels else None
        elif thinking_config.thinking_budget is not None:
            # Only the two budgets the contract has a word for. A fixed budget -- `128` -- is
            # neither: describing it as `True` would publish a baseline saying "let the model
            # decide", and saving that baseline back would apply an automatic budget and delete the
            # limit the code set. Left out for the same reason a fractional `top_k` is.
            settings['thinking'] = _BUDGET_MEANINGS.get(thinking_config.thinking_budget)
    return {name: value for name, value in settings.items() if value is not None}
