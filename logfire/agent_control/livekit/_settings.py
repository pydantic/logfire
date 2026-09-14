"""Lowering the contract's eleven settings into what a LiveKit plugin actually takes.

LiveKit has no canonical model-settings object: each plugin keeps a private `_opts` dataclass filled
from its own constructor, and the only per-request channel is `LLM.chat(extra_kwargs=...)`, which the
plugin spreads into the provider call under that provider's own names. So this module is a table per
plugin family, and every canonical key a family has no name for is reported rather than dropped.

One gotcha shapes everything here. Each plugin's `chat()` starts from `extra_kwargs` and *then* writes
its constructor values over the top, so a value set on the plugin constructor beats the published one
for the same key. That is backwards from the precedence Agent Control wants, cannot be fixed from
outside the plugin, and is therefore reported when it happens rather than left to be discovered.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from livekit.agents import llm
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils.misc import is_given


@dataclass(frozen=True)
class Plugin:
    """What one LiveKit plugin family can be told, in the contract's vocabulary."""

    name: str
    """The family, for the model id the baseline publishes and for messages."""
    extra_kwargs: Mapping[str, str] = field(default_factory=dict[str, str])
    """Canonical setting -> the name this plugin's `chat(extra_kwargs=...)` wants it under."""
    thinking: str | None = None
    """The `extra_kwargs` key an effort level lowers to, or `None` where the family has no equivalent."""
    parallel_tool_calls: bool = True
    """Whether the plugin maps `chat(parallel_tool_calls=...)` onto its provider at all."""

    @property
    def supported(self) -> frozenset[str]:
        """The canonical keys this family can apply, for `apply_settings(supported=...)`."""
        keys = {*self.extra_kwargs, 'timeout'}
        if self.thinking is not None:
            keys.add('thinking')
        if self.parallel_tool_calls:
            keys.add('parallel_tool_calls')
        return frozenset(keys)


_OPENAI = Plugin(
    name='openai',
    extra_kwargs={
        'max_tokens': 'max_completion_tokens',
        'temperature': 'temperature',
        'top_p': 'top_p',
        'seed': 'seed',
        'presence_penalty': 'presence_penalty',
        'frequency_penalty': 'frequency_penalty',
        'stop_sequences': 'stop',
    },
    # No `thinking`: the plugin's own constructor writes `reasoning_effort` for every model that
    # takes one -- `'none'` or `'minimal'`, so a published value always loses the collision -- and
    # OpenAI answers `400 Unrecognized request argument supplied: reasoning_effort` for every model
    # that does not. Both observed against the live API; there is no model where sending it works.
)

_INFERENCE = replace(_OPENAI, thinking='reasoning_effort')
"""LiveKit Inference, which speaks Chat Completions too and types its `extra_kwargs` as OpenAI's.

It differs from the plugin in the one place that matters for `thinking`: it never writes
`reasoning_effort` itself, so a published effort level reaches a reasoning model rather than losing
to the constructor. That is the one row in this module not observed against a live request -- driving
LiveKit Inference needs a LiveKit project's credentials, which the tests do not have.
"""

PLUGINS = {
    'livekit.plugins.openai': _OPENAI,
    'livekit.agents.inference': _INFERENCE,
    'livekit.plugins.anthropic': Plugin(
        name='anthropic',
        # No `max_tokens`: the plugin writes `extra['max_tokens']` unconditionally, defaulting to 1024,
        # so a published value for it would be overwritten on every request rather than merely losing
        # to an explicit constructor value. Reporting it is the only honest option.
        extra_kwargs={
            'temperature': 'temperature',
            'top_p': 'top_p',
            'top_k': 'top_k',
            'stop_sequences': 'stop_sequences',
        },
    ),
    'livekit.plugins.google': Plugin(
        name='google',
        # No `presence_penalty` or `frequency_penalty`: the plugin forwards both, and the Gemini API
        # answers `400 Penalty is not enabled for models/<model>` for them. Observed against the live
        # API on `gemini-2.5-flash` and `gemini-2.5-flash-lite`; sending them fails the request.
        extra_kwargs={
            'max_tokens': 'max_output_tokens',
            'temperature': 'temperature',
            'top_p': 'top_p',
            'top_k': 'top_k',
            'seed': 'seed',
            'stop_sequences': 'stop_sequences',
        },
        # `chat()` accepts `parallel_tool_calls` and maps it nowhere.
        parallel_tool_calls=False,
        # `thinking_config` takes a token budget on Gemini 2.5 and a level on Gemini 3, and the plugin
        # *raises* when it is handed the wrong one for the model. An effort level the contract carries
        # is not safe to send without knowing which, and a request that fails is worse than a setting
        # that stays code-defined.
    ),
}
"""Plugin families by the module their `LLM` class is defined under."""

UNKNOWN = Plugin(name='', extra_kwargs={})
"""Any other `llm.LLM` -- a community plugin, a `FallbackAdapter`, a test double.

Only what `LLM.chat` itself defines is applied: `parallel_tool_calls` and the connection timeout are
part of the base signature, while every provider-native name is this table's guess to make and it has
none to make here.
"""


def plugin_for(model: llm.LLM | llm.RealtimeModel) -> Plugin:
    """The family `model` belongs to, by where the class it inherits its `chat()` from is defined.

    The whole ancestry rather than the class itself, because a plugin's `LLM` is routinely wrapped:
    `openai.LLM.with_azure` and friends return the same class, and an application that subclasses one
    to log or retry around `chat()` is still sending that provider's request.
    """
    for ancestor in type(model).__mro__:
        module = ancestor.__module__
        for prefix, plugin in PLUGINS.items():
            if module == prefix or module.startswith(f'{prefix}.'):
                return plugin
    return UNKNOWN


def constructor_value(model: llm.LLM | llm.RealtimeModel, name: str) -> Any:
    """What the plugin's constructor already set for the `extra_kwargs` key `name`, or `NOT_GIVEN`.

    Reaching into `_opts` is the only way to see a collision coming: the plugins expose no getter, and
    the alternative is letting a published setting silently lose to code on every request.
    """
    opts = getattr(model, '_opts', None)
    extra_kwargs: Any = getattr(opts, 'extra_kwargs', None)
    if isinstance(extra_kwargs, dict):
        # LiveKit Inference keeps its whole per-request patch in one dict rather than in named fields.
        return extra_kwargs.get(name, NOT_GIVEN)
    return getattr(opts, name, NOT_GIVEN)


@dataclass(frozen=True)
class Lowered:
    """The published settings, in the three shapes `LLM.chat` takes them in."""

    extra_kwargs: dict[str, Any] = field(default_factory=dict[str, Any])
    """Provider-native names, spread into the request by the plugin."""
    parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN
    """A first-class `chat()` argument, and the one setting a published value reliably wins on."""
    timeout: float | None = None
    """Seconds, applied by narrowing the session's `APIConnectOptions` for this request."""


def lower(settings: Mapping[str, Any], model: llm.LLM, plugin: Plugin) -> tuple[Lowered, list[str]]:
    """Lower canonical settings for `model`, with the collisions the plugin will win to report.

    `settings` has already been filtered to the keys the family supports, so everything here has a
    name to go under; what is left to decide is whether the constructor already claimed that name, and
    whether an effort level has a level-shaped knob to go into.
    """
    natives = dict(plugin.extra_kwargs)
    if plugin.thinking is not None:
        natives['thinking'] = plugin.thinking

    extra_kwargs: dict[str, Any] = {}
    parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN
    collisions: list[str] = []
    for canonical, value in settings.items():
        if canonical == 'timeout':
            continue
        if canonical == 'parallel_tool_calls':
            parallel_tool_calls = value
            continue
        if canonical == 'thinking' and not isinstance(value, str):
            # `True`/`False` names no effort level, and the plugins take a level or nothing.
            collisions.append(
                f'Managed agent config sets {canonical!r} to {value!r}, which the LiveKit '
                f'{plugin.name} plugin has no on/off equivalent for -- it takes an effort level; '
                'that setting is not applied.'
            )
            continue
        native = natives[canonical]
        if is_given(constructor_value(model, native)):
            collisions.append(
                f'Managed agent config sets {canonical!r} to {value!r}, but the LiveKit {plugin.name} '
                f'plugin was constructed with {native!r} and writes its own value over the per-request '
                'one; that setting is not applied. Leave it off the constructor to manage it from Logfire.'
            )
            continue
        extra_kwargs[native] = value
    return Lowered(extra_kwargs, parallel_tool_calls, settings.get('timeout')), collisions


def code_settings(model: llm.LLM, plugin: Plugin) -> dict[str, Any]:
    """The settings the plugin was constructed with, in canonical names.

    Read back through the same table that lowers them, so this describes exactly the knobs a
    published value would reach. `timeout` is not here: LiveKit keeps it on the session's connection
    options rather than on the model, so whoever needs it reads it from there.

    Values are passed on as the plugin holds them, including ones the contract has no room for -- an
    OpenAI reasoning model's default `reasoning_effort` of `'none'` is not one of the effort levels.
    Naming it and letting `canonical_settings` drop and report it is the contract's rule for an
    unrepresentable value; deciding here would be this package approximating on its own.
    """
    settings: dict[str, Any] = {}
    for canonical, native in plugin.extra_kwargs.items():
        value = constructor_value(model, native)
        if is_given(value):
            settings[canonical] = value
    if plugin.parallel_tool_calls:
        value = constructor_value(model, 'parallel_tool_calls')
        if is_given(value):
            settings['parallel_tool_calls'] = value
    if plugin.thinking is not None:
        effort = constructor_value(model, plugin.thinking)
        if is_given(effort):
            settings['thinking'] = effort
    return settings


def carry_settings(code_model: llm.LLM, plugin: Plugin) -> tuple[dict[str, Any], list[str]]:
    """The code model's settings that `plugin` can be told, and messages for the ones it cannot.

    A published `model` is a fresh plugin instance carrying its class's defaults, so the temperature
    and token budget someone chose in code would silently go away with the model they were set on --
    turning "run this on a different model" into "and reset everything else". They are the code side
    of the same contract, so they move across as per-request settings, underneath the published
    `settings` section, which is what overriding code means.

    A setting the replacement's plugin family has no name for (an Anthropic `top_k` on the way to
    OpenAI) cannot move, and is reported rather than dropped: the agent really is about to run
    without something its code asked for.
    """
    carried: dict[str, Any] = {}
    lost: list[str] = []
    for canonical, value in code_settings(code_model, plugin_for(code_model)).items():
        if canonical in plugin.supported:
            carried[canonical] = value
        else:
            lost.append(
                f'This agent is built with {canonical}={value!r}, which the LiveKit {plugin.name or "unknown"} '
                'plugin the managed agent config moves it to has no equivalent for; the published model runs '
                'without it.'
            )
    return carried, lost
