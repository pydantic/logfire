"""The model and the settings, in both directions: options -> baseline, and published value -> options.

The Claude Agent SDK has no sampling knobs at all. `ClaudeAgentOptions` carries no `temperature`,
`max_tokens`, `top_p`, `top_k`, `seed`, `stop_sequences`, penalties, or `parallel_tool_calls`: those
are chosen inside the `claude` CLI, and the SDK's only lever on them is the environment it spawns the
CLI with. So of the contract's eleven canonical settings this adapter can apply three -- `thinking`
natively, and `max_tokens` and `timeout` through the CLI's own environment variables -- and reports
the rest rather than pretending.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import EffortLevel, ThinkingConfig

from logfire.agent_control import to_milliseconds

SUPPORTED_SETTINGS = frozenset({'max_tokens', 'thinking', 'timeout'})
"""The canonical settings keys this framework has a knob for; `apply_settings` reports the others."""

MAX_OUTPUT_TOKENS_ENV = 'CLAUDE_CODE_MAX_OUTPUT_TOKENS'
"""The CLI environment variable that caps output tokens. The CLI clamps it to the model's own limit."""

TIMEOUT_ENV = 'API_TIMEOUT_MS'
"""The CLI environment variable holding the per-request API timeout, in milliseconds."""

ANTHROPIC_PROVIDER = 'anthropic'
"""The one provider a `provider:model` string may name here; the CLI picks its provider from `env`."""

_EFFORT_FOR_THINKING: dict[str, EffortLevel] = {
    # The contract's lowest level has no counterpart: `EffortLevel` starts at `low`, so `minimal`
    # lands there rather than being dropped, which is the nearest thing the CLI can actually do.
    'minimal': 'low',
    'low': 'low',
    'medium': 'medium',
    'high': 'high',
    'xhigh': 'xhigh',
}


def baseline_model(options: ClaudeAgentOptions) -> str | None:
    """The code-defined model as a canonical `provider:model` string.

    Every model this SDK can name is an Anthropic one -- a model id or an alias like `sonnet` -- since
    Bedrock, Vertex, and the rest are selected by environment variables on the CLI subprocess rather
    than by the model string. So the provider is always `anthropic`, and a `None` model (the CLI's own
    default, chosen from settings or `ANTHROPIC_MODEL`) is not knowable from here at all.
    """
    return None if options.model is None else f'{ANTHROPIC_PROVIDER}:{options.model}'


def managed_model(model: str) -> tuple[str | None, str | None]:
    """Lower a published `provider:model` string to what `ClaudeAgentOptions.model` takes.

    Returns the model to set and, when there is none, the reason to report. A string with no provider
    is passed through untouched so a framework-native id keeps working, and any provider other than
    `anthropic` is refused rather than silently truncated: this SDK's provider is a property of the
    environment the CLI runs in, not of the model string, so applying the model half of
    `bedrock:claude-fable-5-1` would send an Anthropic request under a name meant for Bedrock.
    """
    provider, separator, name = model.partition(':')
    if not separator:
        return model, None
    if provider == ANTHROPIC_PROVIDER:
        return name, None
    return None, (
        f'Managed agent config selects model {model!r}, but the Claude Agent SDK takes an Anthropic '
        f'model id and chooses its provider from the environment the CLI runs in; that section is not '
        'applied.'
    )


def _thinking_from(options: ClaudeAgentOptions) -> bool | str | None:
    """The code's `thinking`/`effort` pair as the contract's single `thinking` value.

    `effort` wins where both are set, because it is the finer statement of the same thing: a level
    describes the agent better than "thinking is on" does.

    The level is passed through as the CLI spells it, so a level the contract has no name for --
    `'max'` -- is left out of the baseline and warned about by `canonical_settings` rather than
    described as the nearest one that fits. `'max'` is not `'xhigh'`, and a baseline is the one
    artifact the Logfire editor presents as the truth about the code.
    """
    if options.effort is not None:
        return options.effort
    thinking = options.thinking
    if thinking is None:
        return None
    # `enabled` carries a token budget the contract cannot express, so it reports the part it can.
    return thinking['type'] != 'disabled'


def _int_env(options: ClaudeAgentOptions, name: str) -> int | None:
    """One CLI environment variable as an integer, or `None` when it is absent or not a number."""
    value = options.env.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        # The environment is the user's, and a value the CLI itself would reject is not this
        # adapter's to report: it just is not something the baseline can describe.
        return None


def baseline_settings(options: ClaudeAgentOptions) -> dict[str, Any]:
    """The canonical settings `options` states, for the baseline the Logfire editor diffs against."""
    settings: dict[str, Any] = {}
    thinking = _thinking_from(options)
    if thinking is not None:
        settings['thinking'] = thinking
    max_tokens = _int_env(options, MAX_OUTPUT_TOKENS_ENV)
    if max_tokens is not None:
        settings['max_tokens'] = max_tokens
    timeout_ms = _int_env(options, TIMEOUT_ENV)
    if timeout_ms is not None:
        settings['timeout'] = timeout_ms / 1000
    return settings


def apply_managed_settings(options: ClaudeAgentOptions, patch: dict[str, Any]) -> dict[str, Any]:
    """Lower a settings patch to `ClaudeAgentOptions` changes.

    `patch` is what `apply_settings(config, supported=SUPPORTED_SETTINGS)` returned, so every key here
    is one this framework has a knob for. A published `thinking` sets both `thinking` and `effort`
    together, since the two are one statement in the contract and leaving the code's half in place is
    how you get `effort='high'` on an agent whose thinking a published value just turned off.
    """
    changes: dict[str, Any] = {}
    env = dict(options.env)

    if 'thinking' in patch:
        thinking: bool | str = patch['thinking']
        if thinking is False:
            disabled: ThinkingConfig = {'type': 'disabled'}
            changes['thinking'] = disabled
            changes['effort'] = None
        else:
            adaptive: ThinkingConfig = {'type': 'adaptive'}
            changes['thinking'] = adaptive
            changes['effort'] = None if thinking is True else _EFFORT_FOR_THINKING[thinking]

    if 'max_tokens' in patch:
        env[MAX_OUTPUT_TOKENS_ENV] = str(patch['max_tokens'])
    if 'timeout' in patch:
        # `to_milliseconds` is the contract's own conversion, so the same published timeout becomes
        # the same integer here as in every other adapter and in the TypeScript core.
        env[TIMEOUT_ENV] = str(to_milliseconds(patch['timeout']))
    if env != options.env:
        changes['env'] = env
    return changes
