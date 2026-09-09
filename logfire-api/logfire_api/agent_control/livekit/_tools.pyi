from .. import AgentConfig as AgentConfig, AppliedTools as AppliedTools, OnUnmatched as OnUnmatched, ToolDef as ToolDef, ToolKey as ToolKey, apply_tool_definitions as apply_tool_definitions
from _typeshed import Incomplete
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping, Sequence
from livekit.agents import llm
from livekit.agents.types import NotGivenOr
from typing import Any

NO_RUN_CONTEXT: Incomplete

def toolset_ids(tools: Iterable[llm.Tool | llm.Toolset]) -> dict[object, str]:
    """Map each tool to the id of the toolset it came from, so an override can be narrowed to one group.

    Keyed by the tool object rather than its name because the same name can legitimately appear in two
    toolsets, and because that is what the flat list `llm_node` receives can be looked up by -- the
    flattening the framework does before the hook drops the grouping entirely.
    """
def managed_tools(tools: Sequence[llm.Tool]) -> Iterator[tuple[int, Any]]:
    """The tools Agent Control can edit, with their position in the list the model is shown."""
def reserved_names(tools: Sequence[llm.Tool]) -> set[str]:
    """The advertised names a rename must not take: the tools this package cannot edit.

    A `ProviderTool` -- web search, code execution -- is advertised to the model under its own id and
    has no definition of ours to patch, so a rename onto that id would leave two tools answering to
    one name and a call nothing can route.
    """
def tool_def(tool: Any, toolset: str | None, *, with_schema: bool) -> ToolDef:
    """One tool as the model is shown it.

    `with_schema` is a cost, not a detail: building a `@function_tool`'s schema means building a
    pydantic model from its signature, so it is done for the tools a published config actually patches
    rather than for every tool on every turn. A tool nothing patches needs only its name to be routed.
    """
def bridge(tool: llm.FunctionTool[..., Any], name: str) -> Callable[..., Awaitable[Any]]:
    """A raw-tool function that runs `tool` the way LiveKit would have run it.

    The one clone this package makes that is not the tool's own kind is a `@function_tool` carrying a
    patched *parameter* schema, which has to go out as a raw-schema tool. On the stateless path that
    clone is only ever advertised, but a realtime session's tool list is the list its dispatcher uses,
    and LiveKit hands a raw tool the model's arguments in a single `raw_arguments` dict -- so a clone
    wrapping `get_weather(city: str)` directly would fail to bind, and would have skipped the argument
    validation and `RunContext` injection the original was getting.

    This closes over the original tool and asks LiveKit for exactly that work, so patching a parameter
    description changes what the model is told and nothing about what runs.
    """
def clone(tool: Any, definition: ToolDef, *, schema_patched: bool) -> llm.Tool:
    """A tool that advertises `definition` to the model and otherwise behaves like `tool`.

    A rename or a reworded description is applied on the tool's own kind, so a `@function_tool` keeps
    deriving its schema the way the plugin would have. Patching a *parameter* description cannot: the
    schema is derived from the signature and there is nowhere to put the new text, so that one tool is
    advertised as a raw-schema tool carrying the patched schema, wrapped around the `bridge` that
    keeps its execution identical. That drops the strict-mode schema the OpenAI and Anthropic plugins
    would otherwise send for it -- see the README's known limits.
    """
def advertise(tools: Sequence[llm.Tool], config: AgentConfig, toolsets: Mapping[object, str], *, on_unmatched: OnUnmatched) -> tuple[list[llm.Tool], AppliedTools]:
    """The tools to send this turn, and the routing the core worked out for them.

    The list the hook was handed is left alone. LiveKit syncs edits to it back into the turn's
    `ToolContext`, which is what dispatches a call, so renaming in place would rename the tool the
    implementation answers to as well; advertising a separate list keeps the rename on the wire only.
    """
def forward_names(applied: AppliedTools) -> dict[str, str]:
    """Code-side name -> the name that tool is advertised under, for the tools a config renamed.

    `AppliedTools.forward` is keyed on `(toolset, name)` for a framework where a bare name is not an
    identity. LiveKit's is: dispatch, `tool_choice`, and every history entry name a tool by a bare
    string, and two tools sharing one are already unroutable before Agent Control sees them.
    """
def renamed(applied: AppliedTools) -> list[tuple[ToolKey, str]]:
    """Every tool a config renamed, as `(toolset, code name)` and the name it is advertised under."""
def rename_calls(chat_ctx: llm.ChatContext, forward: Mapping[str, str]) -> None:
    """Rename past tool calls in the outgoing context to the names the model is being shown.

    Without this a renamed tool contradicts itself: the schema offers `lookup_weather` while the
    history shows the assistant calling `get_weather`, a tool that no longer exists as far as the model
    can tell. Items are replaced rather than mutated -- the turn's context is a shallow copy of the
    stored history, so editing an item in place would rewrite the conversation the agent keeps.
    """
def rename_tool_choice(tool_choice: NotGivenOr[llm.ToolChoice], forward: Mapping[str, str]) -> NotGivenOr[llm.ToolChoice]:
    """Point a forced `tool_choice` at the name the model is being shown for that tool.

    A `tool_choice` naming `get_weather` is a decision the code made about which tool to force, not a
    managed setting -- so it has to survive a rename rather than be silently unforced by one. Left
    exactly as it was when it names no tool (`'auto'`, `'required'`, `'none'`) or names one nothing
    renamed.
    """
