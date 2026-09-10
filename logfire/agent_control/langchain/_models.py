"""Translating between the contract's `provider:model` string and LangChain's own model convention.

The two conventions are the same shape and mostly the same words, which is why this is a table of
five entries rather than a parser: LangChain also writes `provider:model`, splits on the first `:`
when the prefix is one it knows, and otherwise infers the provider from the model name. Only the
provider ids themselves differ, and only for five providers.
"""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from logfire.agent_control import AgentControl

PROVIDER_ALIASES = {
    'google': 'google_genai',
    'google-cloud': 'google_vertexai',
    'mistral': 'mistralai',
    'azure': 'azure_openai',
    # LangChain has both `bedrock` (the InvokeModel API) and `bedrock_converse`; the contract's
    # `bedrock` is the Converse API, which is the one that speaks tools the same way everywhere.
    'bedrock': 'bedrock_converse',
}
"""Contract provider id -> LangChain provider id, for the ids the two spell differently.

Every other provider is spelled identically by both (`openai`, `anthropic`, `groq`, `deepseek`,
`openrouter`, `xai`, `ollama`, `huggingface`, `cohere`, `together`, `fireworks`, `litellm`, ...),
and a string with no `:` is passed through for LangChain to infer, so a LangChain-native model id
keeps working.

These are the current ids, and this is also the table a baseline is written with: a model read off
a LangChain integration goes up to Logfire spelled the way the contract spells it today.
"""

LEGACY_PROVIDER_ALIASES = {
    'google-gla': 'google_genai',
    'google-vertex': 'google_vertexai',
}
"""Contract provider ids that were renamed, still accepted on the way in.

`google-gla` and `google-vertex` are what the Gemini API and Vertex were called before they became
`google` and `google-cloud`, and a config published against an agent that predates the rename still
carries the old spelling. They are read and never written: such a value keeps working, and nothing
this adapter publishes uses them.
"""

_LANGCHAIN_PROVIDERS = {langchain: contract for contract, langchain in PROVIDER_ALIASES.items()}


def to_langchain_model_id(model: str) -> str:
    """A contract `provider:model` string in LangChain's spelling."""
    provider, separator, name = model.partition(':')
    if not separator:
        return model
    langchain = PROVIDER_ALIASES.get(provider) or LEGACY_PROVIDER_ALIASES.get(provider, provider)
    return f'{langchain}:{name}'


def build_model(model: str, control: AgentControl) -> BaseChatModel | None:
    """The model a published `model` names, or `None` to keep the model the agent was built with.

    `init_chat_model` is LangChain's own resolution, so a published string reaches exactly the class
    the user would have gotten by passing it to `create_agent`. It raises for a provider it cannot
    infer and for one whose integration package is not installed -- both of which are a published
    value the agent is not applying rather than a reason to take the agent down, so they go through
    the same `on_unmatched` policy as everything else Logfire shows and the agent does not do.
    """
    model_id = to_langchain_model_id(model)
    try:
        return init_chat_model(model_id)
    except Exception as exc:
        control.report_unmatched(
            f'Managed agent config sets model {model!r}, which LangChain could not build as '
            f'{model_id!r}: {exc}; that section is not applied and the agent keeps the model it was built with.'
        )
        return None


def read_model_id(model: BaseChatModel) -> str | None:
    """The `provider:model` string describing the model the agent was built with, for the baseline.

    LangChain keeps no model identifier on a `BaseChatModel` -- the attribute holding the model name
    is `model`, `model_name`, `model_id` or `deployment_name` depending on the integration -- so the
    one generic source is the pair every integration reports for tracing. It is private API, and an
    integration that raises from it costs the baseline its `model` line and nothing else.
    """
    try:
        params: dict[str, Any] = dict(model._get_ls_params())  # type: ignore[reportPrivateUsage]
    except Exception:
        return None
    provider = params.get('ls_provider')
    name = params.get('ls_model_name')
    if not isinstance(provider, str) or not isinstance(name, str):
        return None
    return f'{_LANGCHAIN_PROVIDERS.get(provider, provider)}:{name}'
