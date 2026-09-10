from collections.abc import Mapping
from langchain_core.language_models import BaseChatModel
from logfire.agent_control import AgentConfig as AgentConfig, OnUnmatched as OnUnmatched, apply_settings as apply_settings, canonical_settings as canonical_settings
from typing import Any

PARALLEL_TOOL_CALLS: str

def read_settings(model: BaseChatModel) -> dict[str, Any]:
    """The canonical settings the agent's model was built with, for the baseline.

    Only the contract's own keys, and only values it can hold: an integration's provider-specific
    fields and its `model_kwargs` -- where API keys, signed bodies and custom headers end up -- are
    not part of the contract, and the baseline is readable by everyone in the Logfire project.
    Filtering both is the core's `canonical_settings`, which also says out loud what it left out: a
    value the contract cannot describe -- Anthropic's `reasoning_effort='max'` -- is reported rather
    than published as the nearest thing that fits.
    """
def carry_settings(code: BaseChatModel, published: BaseChatModel) -> dict[str, Any]:
    """The code model's canonical settings, as kwargs the published model takes.

    A published `model` replaces the instance the agent was built with, and the replacement carries
    its class's defaults rather than the temperature and token budget someone chose in code. Those
    are the code side of the same contract, so they move across as request settings -- underneath
    the published `settings` section, which is what overriding code means. A setting the new
    provider has no kwarg for (an Anthropic `top_k` on the way to OpenAI) does not move: it was
    never a thing that model could do.
    """
def lower_settings(model: BaseChatModel, config: AgentConfig, *, has_tools: bool, on_unmatched: OnUnmatched) -> dict[str, Any]:
    """The published `settings` section as `model_settings` kwargs this model understands.

    Every canonical key this model has no kwarg for is reported rather than dropped, which is the
    point of naming them: a `top_k` published against an OpenAI agent, or a `seed` against an
    Anthropic one, is a setting someone can see in Logfire and the agent is not applying.
    """
def align_run_settings(model: BaseChatModel, run: Mapping[str, Any], published: Mapping[str, Any]) -> dict[str, Any]:
    """The run's settings, with any second spelling of a published key rewritten to the first.

    An integration declares a setting under one name and takes another as its alias -- `stop` and
    `stop_sequences` are each other's, in opposite directions on OpenAI and Anthropic, and OpenAI's
    `timeout` is really `request_timeout` -- and `lower_settings` can only advertise one of them. A
    middleware that reached for the other spelling would otherwise not collide with the published
    value at all: both keys survive the merge and go out together, which on OpenAI puts
    `stop_sequences` in the request body next to `stop`, and that is not a parameter of the API.

    Only a key the published section also sets is rewritten, and only onto the spelling that
    section is already using, so a request with nothing published for that setting still carries
    exactly what the middleware ahead of this one wrote.
    """
def canonical_name(model: BaseChatModel, kwarg: str) -> str:
    """The contract's name for a kwarg this model takes, for saying which published setting it is.

    The two are the same word for most of the eleven, and are not for the ones an integration spells
    its own way -- `stop_sequences` as `stop`, `thinking` as `reasoning_effort` -- which are exactly
    the ones a message naming only the kwarg would leave someone hunting for in the Logfire editor.
    A kwarg that is not one of the mapped settings is its own canonical name: `parallel_tool_calls`
    is a `bind_tools()` parameter rather than a model field, so it never goes through that table.
    """
