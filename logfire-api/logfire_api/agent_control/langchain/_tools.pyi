from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from logfire.agent_control import AgentConfig as AgentConfig, OnUnmatched as OnUnmatched, ToolDef as ToolDef, apply_tool_definitions as apply_tool_definitions
from typing import Any, TypeVar

MessageT = TypeVar('MessageT', bound=BaseMessage)
LangChainTool = BaseTool | dict[str, Any]

@dataclass(frozen=True)
class AppliedTools:
    """The tools to advertise, and the two directions a rename has to be translated in."""
    tools: list[LangChainTool]
    forward: dict[str, str]
    reverse: dict[str, str]

def read_tools(tools: Sequence[LangChainTool]) -> list[ToolDef]:
    """The code-side tools a request advertises, as the contract describes them.

    Provider built-ins -- the `dict` entries `create_agent` passes through to a server-side tool
    like web search -- are left out. They have no code-side implementation to route a rename back
    to, and their shape is the provider's, not LangChain's, so there is nothing here to manage.

    LangChain has no notion of a toolset, so no tool reports one and an override that names one
    matches nothing. That is reported, not silently ignored.
    """
def apply_tools(tools: Sequence[LangChainTool], config: AgentConfig, *, on_unmatched: OnUnmatched) -> AppliedTools:
    """Advertise the request's tools with the managed names and wording a config published.

    A patched tool is advertised as a copy of the code tool with the model-facing fields replaced,
    so it stays a `BaseTool` that `create_agent` binds exactly like the original -- and the original
    object is passed through untouched when nothing patched it, which is what keeps a request with
    no published tool overrides byte-identical to the one the agent would have sent.

    Only the copy is ever advertised. `ToolNode` still holds the code tool, under the code name, and
    executes it; `forward` and `reverse` are how the middleware keeps the rename between itself and
    the model.
    """
def rename_tool_choice(tool_choice: Any, names: Mapping[str, str]) -> Any:
    """A `tool_choice` naming one of the code's tools, saying the name this request advertises.

    A forced tool choice is a decision the code made about its own tools, so it has to survive an
    overlay that renames one of them: left alone, it names a tool the model is no longer shown and
    the provider rejects the request. Both spellings the integrations take are translated -- the bare
    name, and the dict OpenAI and Anthropic each wrap it in -- and anything else is passed through,
    including the `'auto'`/`'any'`/`'none'` words, which are not tool names.
    """
def rename_tool_calls(messages: Sequence[MessageT], names: Mapping[str, str]) -> list[MessageT]:
    """Every call in a conversation, saying the names of the side it is about to be read by.

    Used in both directions with the mapping for that direction: forward over the history a request
    replays, so the model sees the names it was shown; back over the model's reply, so the graph
    dispatches, stores, and traces the names the code gave its tools. A message that calls nothing
    renamed is the object that came in, so nothing else about the conversation is rewritten.
    """
