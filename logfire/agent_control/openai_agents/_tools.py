"""Advertising managed tool definitions, and routing what the model calls back to the code tool.

A rename is the only managed value that outlives the request it was applied to. The SDK looks a
returned `function_call` up by name in the tool list *it* assembled -- not the one this adapter handed
the model -- and it replays that call to the model on the next turn as an input item. So a rename is
four edits, not one: advertise the new name, put the code name back on the way out, put the managed
name back on the history going in, and put it on the *other* place a name reaches the model, a
`tool_choice` that forces one. Miss the second and the runner cannot find the tool; miss the third and
the model is shown itself calling a tool it was never offered; miss the fourth and a request forces a
tool that is no longer advertised under that name.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ToolChoice
from agents.tool import FunctionTool, Tool, ToolOrigin, ToolOriginType, get_function_tool_origin
from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
)

from .. import AppliedTools, ToolDef

AGENT_TOOLSET = '<agent>'
"""The group name for a tool the agent declares itself, as opposed to one a server contributed."""

TOOL_CHOICE_MODES = frozenset({'auto', 'required', 'none'})
"""The `tool_choice` values that are instructions rather than names, so no rename ever touches them.

`ModelSettings.tool_choice` is one string for both, and the SDK reads these three as modes even for an
agent whose tool happens to be called `auto`. Reading them the same way here is what keeps a rename
from turning "let the model choose" into "call the tool formerly known as auto".
"""


def _toolset(tool: FunctionTool) -> str:
    """Where a tool came from, as a name the Logfire UI can group a long list by.

    The SDK already tracks this for tracing (`ToolOrigin`), so the grouping is the framework's own
    answer rather than one inferred from tool names: tools an MCP server contributed are named by
    that server, and an agent exposed through `Agent.as_tool` is named by that agent. Two servers
    that both advertise a `search` are what makes this worth carrying -- with the server in the
    group, a published override can patch one of them and leave the other alone.
    """
    origin = get_function_tool_origin(tool) or ToolOrigin(type=ToolOriginType.FUNCTION)
    if origin.type is ToolOriginType.MCP and origin.mcp_server_name is not None:
        return f'mcp:{origin.mcp_server_name}'
    if origin.type is ToolOriginType.AGENT_AS_TOOL and origin.agent_name is not None:
        return f'agent:{origin.agent_name}'
    return AGENT_TOOLSET


def tool_definitions(tools: Iterable[Tool]) -> list[ToolDef]:
    """The LLM-facing definition of every tool a published config can patch, in the order advertised.

    Only `FunctionTool`s are included. The hosted tools -- web search, file search, the computer and
    code-interpreter tools, hosted MCP -- are configuration for something running on OpenAI's side,
    with no description or schema the SDK could show the model differently, so there is nothing for
    the editor to offer and listing them would only imply there is.
    """
    return [
        ToolDef(
            name=tool.name,
            description=tool.description or None,
            parameters_json_schema=tool.params_json_schema,
            toolset=_toolset(tool),
        )
        for tool in tools
        if isinstance(tool, FunctionTool)
    ]


def reserved_names(tools: Iterable[Tool], handoffs: Iterable[Handoff]) -> set[str]:
    """The names this request advertises that no rename may take, because nothing here can move them.

    A handoff is a tool to the model, and so is a hosted tool -- web search, the computer tool, hosted
    MCP -- and neither is in the editable list this adapter builds. The core cannot see them, so a
    rename onto one of their names would advertise two tools under one name and make a call to it
    unroutable; passed as `reserved`, that rename is refused and reported like any other collision.
    """
    return {tool.name for tool in tools if not isinstance(tool, FunctionTool)} | {
        handoff.tool_name for handoff in handoffs
    }


def advertised_names(applied: AppliedTools) -> dict[str, str]:
    """Code-side tool name -> the name it is advertised under, for everything on the way out.

    The core keys its forward map on `(toolset, name)`, because a framework whose runtime names carry
    their toolset can advertise two tools called `search`. This one's cannot: the SDK puts every tool
    in one flat namespace, which is what `collision_scope='global'` says, so a bare code-side name is
    an identity here and the pair collapses to it.
    """
    return {name: advertised for (_, name), advertised in applied.forward.items()}


def rename_tool_choice(tool_choice: ToolChoice | None, advertised: Mapping[str, str]) -> ToolChoice | None:
    """Re-apply a managed name to a `tool_choice` that forces the tool by its code-side name.

    A forced tool choice is a code-defined decision -- this call must use this tool -- and it has to
    survive an overlay that only meant to rename the tool. It is a name in the same namespace as the
    tool list, so it is mapped in the same place and the same direction as the definitions: leave it
    as it is and the request forces a tool the model was never offered, which the provider rejects.
    """
    if not isinstance(tool_choice, str) or tool_choice in TOOL_CHOICE_MODES:
        return tool_choice
    return advertised.get(tool_choice, tool_choice)


def advertise(tools: Sequence[Tool], applied: AppliedTools) -> list[Tool]:
    """The tool list to hand the model: the agent's own, with managed names and descriptions on the copies.

    Copies, because the list belongs to the runner and the `FunctionTool`s in it belong to the agent:
    a rename written through either would outlive this request and reach the next agent that shares
    the tool. Order is the runner's throughout -- it puts MCP tools ahead of the agent's own, and a
    provider caches the prefix a tool list is part of, so reordering would bust that cache per
    request in exchange for nothing.
    """
    definitions = iter(applied.tools)
    advertised: list[Tool] = []
    for tool in tools:
        if not isinstance(tool, FunctionTool):
            advertised.append(tool)
            continue
        definition = next(definitions)
        if (
            definition.name == tool.name
            and (definition.description or '') == tool.description
            and definition.parameters_json_schema is tool.params_json_schema
        ):
            advertised.append(tool)
            continue
        advertised.append(
            replace(
                tool,
                name=definition.name,
                description=definition.description or '',
                params_json_schema=definition.parameters_json_schema,
            )
        )
    return advertised


def rename_history(
    input: str | list[TResponseInputItem], advertised_names: Mapping[str, str]
) -> str | list[TResponseInputItem]:
    """Re-apply managed names to the tool calls already in this run's history.

    The runner records a call under the name the *code* tool has (this adapter put it back there on
    the way out), and replays it as an input item on every later turn. Renaming it forward again is
    what keeps the conversation self-consistent: the model is shown the tool under one name in the
    tool list and in every call it made under that name, whatever the code behind it is called.
    """
    if isinstance(input, str):
        return input
    renamed: list[TResponseInputItem] = []
    changed = False
    for item in input:
        # The union of TypedDicts an input item can be does not share a `name` key, and this needs
        # to read one off whichever member is a function call, so it reads the mapping it is.
        entry = cast('dict[str, Any]', item)
        name = entry.get('name') if entry.get('type') == 'function_call' else None
        advertised = advertised_names.get(name) if isinstance(name, str) else None
        if advertised is None or advertised == name:
            renamed.append(item)
        else:
            renamed.append(cast('TResponseInputItem', {**entry, 'name': advertised}))
            changed = True
    return renamed if changed else input


def _rename_calls(items: Iterable[object], routes: Mapping[str, str]) -> None:
    """Put the code-side name back on every renamed tool call, in place.

    In place because the runner looks the call up by name in its own tool list and then stores that
    same object as the run's record of the call: a copy renamed on the side would leave the original
    -- the one the history and the trace keep -- naming a tool that does not exist in the code.
    """
    for item in items:
        if isinstance(item, ResponseFunctionToolCall):
            code_name = routes.get(item.name)
            if code_name is not None and code_name != item.name:
                item.name = code_name


def rename_response(response: ModelResponse, routes: Mapping[str, str]) -> ModelResponse:
    """Route a renamed tool call in a complete response back to the tool that implements it."""
    _rename_calls(response.output, routes)
    return response


def rename_stream_event(event: TResponseStreamEvent, routes: Mapping[str, str]) -> TResponseStreamEvent:
    """Route renamed tool calls in a streamed event back, wherever an event carries a call.

    Three events do: the two that announce an output item, which is how a streaming caller learns a
    tool was called, and the completed event, whose response is what the runner executes tools from.
    The argument deltas in between carry an item id rather than a name and need nothing.
    """
    if isinstance(event, (ResponseOutputItemAddedEvent, ResponseOutputItemDoneEvent)):
        _rename_calls([event.item], routes)
    elif isinstance(event, ResponseCompletedEvent):
        _rename_calls(event.response.output, routes)
    return event
