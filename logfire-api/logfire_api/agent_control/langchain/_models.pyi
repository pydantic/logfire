from _typeshed import Incomplete
from langchain_core.language_models import BaseChatModel
from logfire.agent_control import AgentControl as AgentControl

PROVIDER_ALIASES: Incomplete
LEGACY_PROVIDER_ALIASES: Incomplete

def to_langchain_model_id(model: str) -> str:
    """A contract `provider:model` string in LangChain's spelling."""
def build_model(model: str, control: AgentControl) -> BaseChatModel | None:
    """The model a published `model` names, or `None` to keep the model the agent was built with.

    `init_chat_model` is LangChain's own resolution, so a published string reaches exactly the class
    the user would have gotten by passing it to `create_agent`. It raises for a provider it cannot
    infer and for one whose integration package is not installed -- both of which are a published
    value the agent is not applying rather than a reason to take the agent down, so they go through
    the same `on_unmatched` policy as everything else Logfire shows and the agent does not do.
    """
def read_model_id(model: BaseChatModel) -> str | None:
    """The `provider:model` string describing the model the agent was built with, for the baseline.

    LangChain keeps no model identifier on a `BaseChatModel` -- the attribute holding the model name
    is `model`, `model_name`, `model_id` or `deployment_name` depending on the integration -- so the
    one generic source is the pair every integration reports for tracing. It is private API, and an
    integration that raises from it costs the baseline its `model` line and nothing else.
    """
