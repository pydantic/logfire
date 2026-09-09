from .. import AppliedTools as AppliedTools, ToolDef as ToolDef
from _typeshed import Incomplete
from agents.handoffs import Handoff as Handoff
from agents.items import ModelResponse, TResponseInputItem as TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ToolChoice
from agents.tool import Tool as Tool
from collections.abc import Iterable, Mapping, Sequence

AGENT_TOOLSET: str
TOOL_CHOICE_MODES: Incomplete

def tool_definitions(tools: Iterable[Tool]) -> list[ToolDef]:
    """The LLM-facing definition of every tool a published config can patch, in the order advertised.

    Only `FunctionTool`s are included. The hosted tools -- web search, file search, the computer and
    code-interpreter tools, hosted MCP -- are configuration for something running on OpenAI's side,
    with no description or schema the SDK could show the model differently, so there is nothing for
    the editor to offer and listing them would only imply there is.
    """
def reserved_names(tools: Iterable[Tool], handoffs: Iterable[Handoff]) -> set[str]:
    """The names this request advertises that no rename may take, because nothing here can move them.

    A handoff is a tool to the model, and so is a hosted tool -- web search, the computer tool, hosted
    MCP -- and neither is in the editable list this adapter builds. The core cannot see them, so a
    rename onto one of their names would advertise two tools under one name and make a call to it
    unroutable; passed as `reserved`, that rename is refused and reported like any other collision.
    """
def advertised_names(applied: AppliedTools) -> dict[str, str]:
    """Code-side tool name -> the name it is advertised under, for everything on the way out.

    The core keys its forward map on `(toolset, name)`, because a framework whose runtime names carry
    their toolset can advertise two tools called `search`. This one's cannot: the SDK puts every tool
    in one flat namespace, which is what `collision_scope='global'` says, so a bare code-side name is
    an identity here and the pair collapses to it.
    """
def rename_tool_choice(tool_choice: ToolChoice | None, advertised: Mapping[str, str]) -> ToolChoice | None:
    """Re-apply a managed name to a `tool_choice` that forces the tool by its code-side name.

    A forced tool choice is a code-defined decision -- this call must use this tool -- and it has to
    survive an overlay that only meant to rename the tool. It is a name in the same namespace as the
    tool list, so it is mapped in the same place and the same direction as the definitions: leave it
    as it is and the request forces a tool the model was never offered, which the provider rejects.
    """
def advertise(tools: Sequence[Tool], applied: AppliedTools) -> list[Tool]:
    """The tool list to hand the model: the agent's own, with managed names and descriptions on the copies.

    Copies, because the list belongs to the runner and the `FunctionTool`s in it belong to the agent:
    a rename written through either would outlive this request and reach the next agent that shares
    the tool. Order is the runner's throughout -- it puts MCP tools ahead of the agent's own, and a
    provider caches the prefix a tool list is part of, so reordering would bust that cache per
    request in exchange for nothing.
    """
def rename_history(input: str | list[TResponseInputItem], advertised_names: Mapping[str, str]) -> str | list[TResponseInputItem]:
    """Re-apply managed names to the tool calls already in this run's history.

    The runner records a call under the name the *code* tool has (this adapter put it back there on
    the way out), and replays it as an input item on every later turn. Renaming it forward again is
    what keeps the conversation self-consistent: the model is shown the tool under one name in the
    tool list and in every call it made under that name, whatever the code behind it is called.
    """
def rename_response(response: ModelResponse, routes: Mapping[str, str]) -> ModelResponse:
    """Route a renamed tool call in a complete response back to the tool that implements it."""
def rename_stream_event(event: TResponseStreamEvent, routes: Mapping[str, str]) -> TResponseStreamEvent:
    """Route renamed tool calls in a streamed event back, wherever an event carries a call.

    Three events do: the two that announce an output item, which is how a streaming caller learns a
    tool was called, and the completed event, whose response is what the runner executes tools from.
    The argument deltas in between carry an item id rather than a name and need nothing.
    """
