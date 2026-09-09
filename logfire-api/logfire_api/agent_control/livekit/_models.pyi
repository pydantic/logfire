from _typeshed import Incomplete
from collections.abc import Callable as Callable
from dataclasses import dataclass
from livekit.agents import llm
from typing import Any

@dataclass(frozen=True)
class PluginModel:
    """How to build one provider's `LLM`, and how to name it back to Logfire."""
    module: str
    kwargs: dict[str, Any] | None = ...
    reuse_client: bool = ...

PLUGIN_MODELS: Incomplete
INFERENCE_PROVIDERS: Incomplete
INFERENCE_CANONICAL: Incomplete

def canonical_id(model: llm.LLM | llm.RealtimeModel, plugin_name: str) -> str:
    """The `provider:model` string that describes `model`, or its own name if nothing classifies it.

    Deliberately not built from `LLM.provider`, which is the API host (`api.openai.com`) or a display
    name (`Vertex AI`) rather than a provider id. A model this adapter cannot classify is published
    untouched, so a framework-native id keeps working when it comes back.
    """
def build(model_id: str, code_model: llm.LLM | llm.RealtimeModel | None) -> llm.LLM:
    """The LLM a published `model` names, built the way the code model was where that is possible.

    A string with no `:` is a framework-native id and goes to LiveKit Inference untouched, which is the
    convention `Agent(llm='openai/gpt-4.1')` already accepts. A `provider:model` prefers the plugin the
    code model already uses -- same class, same client, only the model name different -- then that
    provider's plugin, then LiveKit Inference. Anything left raises, and the caller reports it.
    """
