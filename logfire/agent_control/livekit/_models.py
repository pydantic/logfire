"""Translating between `provider:model` and the three ways LiveKit names a model.

LiveKit has no framework-wide model string. An agent's LLM is a plugin object built from credentials
(`openai.LLM(model='gpt-4.1')`), or a LiveKit Inference model string in `provider/model` form, or
something else entirely. So a published `model` is turned back into an object here, reusing the code
model's client when it can so that a change of model name does not become a change of endpoint,
credentials, or timeouts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from livekit.agents import llm
from livekit.agents.inference import LLM as InferenceLLM


@dataclass(frozen=True)
class PluginModel:
    """How to build one provider's `LLM`, and how to name it back to Logfire."""

    module: str
    """The plugin module its `LLM` class lives in, imported only if a config asks for it."""
    kwargs: dict[str, Any] | None = None
    """Constructor arguments the provider needs beyond the model name."""
    reuse_client: bool = True
    """Whether the plugin takes a `client=`, so a swap can keep the code model's configured one."""


# The google plugin builds its own `genai` client from `vertexai` plus the environment, so neither
# of Google's two APIs can be reached by handing it the code model's client.
_GOOGLE = PluginModel('livekit.plugins.google', reuse_client=False)
_GOOGLE_CLOUD = PluginModel('livekit.plugins.google', {'vertexai': True}, reuse_client=False)

PLUGIN_MODELS = {
    # Current ids.
    'openai': PluginModel('livekit.plugins.openai'),
    'anthropic': PluginModel('livekit.plugins.anthropic'),
    'google': _GOOGLE,
    'google-cloud': _GOOGLE_CLOUD,
    # Legacy ids, accepted but never published. `google-gla` and `google-vertex` were the Gemini API
    # and Vertex provider ids before Pydantic AI v2 renamed them to `google` and `google-cloud`, and
    # a config published against a v1-era agent can still carry them.
    'google-gla': _GOOGLE,
    'google-vertex': _GOOGLE_CLOUD,
}
"""Canonical provider -> the LiveKit plugin that speaks it."""

INFERENCE_PROVIDERS = {
    # Current ids. Vertex is not one: LiveKit Inference serves Gemini through its own account.
    'openai': 'openai',
    'google': 'google',
    'xai': 'xai',
    'deepseek': 'deepseek-ai',
    'moonshotai': 'moonshotai',
    'zai': 'zai',
    # Legacy, as above.
    'google-gla': 'google',
}
"""Canonical provider -> the prefix LiveKit Inference publishes it under in `provider/model`."""

INFERENCE_CANONICAL = {
    'openai': 'openai',
    'google': 'google',
    'xai': 'xai',
    'deepseek-ai': 'deepseek',
    'moonshotai': 'moonshotai',
    'zai': 'zai',
}
"""The inverse, for reading a LiveKit Inference model string back into canonical form."""


def canonical_id(model: llm.LLM | llm.RealtimeModel, plugin_name: str) -> str:
    """The `provider:model` string that describes `model`, or its own name if nothing classifies it.

    Deliberately not built from `LLM.provider`, which is the API host (`api.openai.com`) or a display
    name (`Vertex AI`) rather than a provider id. A model this adapter cannot classify is published
    untouched, so a framework-native id keeps working when it comes back.
    """
    name = model.model
    if isinstance(model, InferenceLLM) and '/' in name:
        prefix, _, rest = name.partition('/')
        return f'{INFERENCE_CANONICAL.get(prefix, prefix)}:{rest}'
    return f'{plugin_name}:{name}' if plugin_name else name


def build(model_id: str, code_model: llm.LLM | llm.RealtimeModel | None) -> llm.LLM:
    """The LLM a published `model` names, built the way the code model was where that is possible.

    A string with no `:` is a framework-native id and goes to LiveKit Inference untouched, which is the
    convention `Agent(llm='openai/gpt-4.1')` already accepts. A `provider:model` prefers the plugin the
    code model already uses -- same class, same client, only the model name different -- then that
    provider's plugin, then LiveKit Inference. Anything left raises, and the caller reports it.
    """
    provider, separator, name = model_id.partition(':')
    if not separator:
        return InferenceLLM(model_id)
    if isinstance(code_model, InferenceLLM) and provider in INFERENCE_PROVIDERS:
        # Already on LiveKit Inference: stay there rather than needing a second provider's credentials.
        return InferenceLLM(f'{INFERENCE_PROVIDERS[provider]}/{name}')
    plugin = PLUGIN_MODELS.get(provider)
    if plugin is not None:
        try:
            llm_class: type[llm.LLM] = import_module(plugin.module).LLM
        except ImportError:
            pass
        else:
            kwargs = dict(plugin.kwargs or {})
            client = getattr(code_model, '_client', None)
            if plugin.reuse_client and isinstance(code_model, llm_class) and client is not None:
                # The same plugin with a different model: keep the base URL, credentials, and HTTP
                # client the agent was built with, so only the model name changes.
                kwargs['client'] = client
            # The plugins share a `model=` keyword and nothing else; `llm.LLM` itself takes no
            # arguments at all, so the class is only a constructor as far as this is concerned.
            return cast('Callable[..., llm.LLM]', llm_class)(model=name, **kwargs)
    if provider in INFERENCE_PROVIDERS:
        return InferenceLLM(f'{INFERENCE_PROVIDERS[provider]}/{name}')
    raise ValueError(f'no LiveKit plugin or LiveKit Inference provider is known for {provider!r}')
