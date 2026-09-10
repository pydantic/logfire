"""Lowering the contract's canonical model settings into the kwargs one LangChain model accepts.

LangChain has no settings type. A `ModelRequest.model_settings` dict is splatted into
`bind_tools()`/`bind()` and ends up in the provider payload as-is, so a key the integration does not
know is not ignored -- it reaches the API and the request fails. That makes "which keys does *this*
model accept" the whole problem, and this module answers it from the model itself rather than from a
table of providers that would be stale the week a new integration ships: a canonical setting is
applied when the model's own class declares a field (or a field alias) for it, under that name.
"""

from __future__ import annotations

import inspect
from collections.abc import Collection
from typing import Any

from langchain_core.language_models import BaseChatModel

from logfire.agent_control import AgentConfig, OnUnmatched, apply_settings, canonical_settings

_KWARGS: dict[str, tuple[str, ...]] = {
    'max_tokens': ('max_tokens',),
    'temperature': ('temperature',),
    'top_p': ('top_p',),
    'top_k': ('top_k',),
    'seed': ('seed',),
    'presence_penalty': ('presence_penalty',),
    'frequency_penalty': ('frequency_penalty',),
    # OpenAI declares the field as `stop` (aliased `stop_sequences`); Anthropic the other way round.
    # Both accept either at call time and both send it as the provider's own spelling.
    'stop_sequences': ('stop', 'stop_sequences'),
    # Neither integration declares a field literally named `timeout`: it is the *alias* of
    # `request_timeout` (OpenAI) and `default_request_timeout` (Anthropic), and the alias is the
    # name the per-call payload is keyed on, so it is the only candidate.
    'timeout': ('timeout',),
    # An effort level. Both major integrations lower `reasoning_effort` to their own reasoning
    # parameter (`reasoning_effort` for OpenAI, `output_config.effort` for Anthropic).
    'thinking': ('reasoning_effort',),
}
"""Canonical setting -> the LangChain kwarg names that mean it, best first."""

PARALLEL_TOOL_CALLS = 'parallel_tool_calls'
"""The one canonical setting that is not a model field but a `bind_tools()` parameter.

`create_agent` splats `model_settings` into `bind_tools()` when the request advertises tools, and
into `bind()` when it does not -- and `bind()` sends the key straight to the provider, where
`parallel_tool_calls` on a request with no tools is an error on both OpenAI and Anthropic. So it is
applied only when the integration names the parameter *and* this request has tools to parallelize.
"""


def _declared_names(model: BaseChatModel) -> set[str]:
    """Every name the model's class accepts for one of its own fields, field names and aliases."""
    names: set[str] = set()
    for name, field in type(model).model_fields.items():
        names.add(name)
        for alias in (field.alias, field.validation_alias):
            if isinstance(alias, str):
                names.add(alias)
    return names


def _kwarg_names(model: BaseChatModel) -> dict[str, str]:
    """Canonical setting -> the kwarg this model takes it as, for the settings it takes at all."""
    declared = _declared_names(model)
    resolved: dict[str, str] = {}
    for setting, candidates in _KWARGS.items():
        for candidate in candidates:
            if candidate in declared:
                resolved[setting] = candidate
                break
    return resolved


def _field_names(model: BaseChatModel) -> dict[str, str]:
    """Canonical setting -> the attribute holding the agent's own value, for reading the baseline."""
    by_alias: dict[str, str] = {}
    for name, field in type(model).model_fields.items():
        by_alias[name] = name
        for alias in (field.alias, field.validation_alias):
            if isinstance(alias, str):
                by_alias.setdefault(alias, name)
    return {setting: by_alias[kwarg] for setting, kwarg in _kwarg_names(model).items()}


def read_settings(model: BaseChatModel) -> dict[str, Any]:
    """The canonical settings the agent's model was built with, for the baseline.

    Only the contract's own keys, and only values it can hold: an integration's provider-specific
    fields and its `model_kwargs` -- where API keys, signed bodies and custom headers end up -- are
    not part of the contract, and the baseline is readable by everyone in the Logfire project.
    Filtering both is the core's `canonical_settings`, which also says out loud what it left out: a
    value the contract cannot describe -- Anthropic's `reasoning_effort='max'` -- is reported rather
    than published as the nearest thing that fits.
    """
    return canonical_settings({setting: getattr(model, field, None) for setting, field in _field_names(model).items()})


def carry_settings(code: BaseChatModel, published: BaseChatModel) -> dict[str, Any]:
    """The code model's canonical settings, as kwargs the published model takes.

    A published `model` replaces the instance the agent was built with, and the replacement carries
    its class's defaults rather than the temperature and token budget someone chose in code. Those
    are the code side of the same contract, so they move across as request settings -- underneath
    the published `settings` section, which is what overriding code means. A setting the new
    provider has no kwarg for (an Anthropic `top_k` on the way to OpenAI) does not move: it was
    never a thing that model could do.
    """
    kwargs = _kwarg_names(published)
    return {kwargs[setting]: value for setting, value in read_settings(code).items() if setting in kwargs}


def lower_settings(
    model: BaseChatModel, config: AgentConfig, *, has_tools: bool, on_unmatched: OnUnmatched
) -> dict[str, Any]:
    """The published `settings` section as `model_settings` kwargs this model understands.

    Every canonical key this model has no kwarg for is reported rather than dropped, which is the
    point of naming them: a `top_k` published against an OpenAI agent, or a `seed` against an
    Anthropic one, is a setting someone can see in Logfire and the agent is not applying.
    """
    kwargs = _kwarg_names(model)
    supported: Collection[str] = _supported(model, config, kwargs, has_tools=has_tools)
    values = apply_settings(config, supported=supported, on_unmatched=on_unmatched)
    return {kwargs.get(setting, setting): value for setting, value in values.items()}


def canonical_name(model: BaseChatModel, kwarg: str) -> str:
    """The contract's name for a kwarg this model takes, for saying which published setting it is.

    The two are the same word for most of the eleven, and are not for the ones an integration spells
    its own way -- `stop_sequences` as `stop`, `thinking` as `reasoning_effort` -- which are exactly
    the ones a message naming only the kwarg would leave someone hunting for in the Logfire editor.
    A kwarg that is not one of the mapped settings is its own canonical name: `parallel_tool_calls`
    is a `bind_tools()` parameter rather than a model field, so it never goes through that table.
    """
    for setting, name in _kwarg_names(model).items():
        if name == kwarg:
            return setting
    return kwarg


def _supported(model: BaseChatModel, config: AgentConfig, kwargs: dict[str, str], *, has_tools: bool) -> set[str]:
    """The canonical keys this model, on this request, actually has a knob for."""
    supported = set(kwargs)
    if config.settings is not None and isinstance(config.settings.thinking, bool):
        # `reasoning_effort` takes a level, and no LangChain integration has an on/off switch that
        # means the same thing on all of them: OpenAI's reasoning models always reason, Anthropic's
        # `thinking` needs a shape that depends on the model generation. A bare `true`/`false` is
        # reported rather than guessed at.
        supported.discard('thinking')
    if has_tools and PARALLEL_TOOL_CALLS in inspect.signature(model.bind_tools).parameters:
        supported.add(PARALLEL_TOOL_CALLS)
    return supported
