"""Reading the tools a request advertises, advertising them under managed names, and translating back.

A rename lives entirely between this adapter and the model. The model is shown the managed name, and
everything on this side of that boundary -- the graph's state, the `ToolNode` that dispatches, any
middleware keyed on a tool's name, the messages a checkpointer writes down -- keeps the name the code
gave the tool. That takes both directions: the reply is translated back before it becomes state, and
the history replayed to the model is translated forward again on the way out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from logfire.agent_control import AgentConfig, OnUnmatched, ToolDef, apply_tool_definitions

MessageT = TypeVar('MessageT', bound=BaseMessage)
"""One message of a conversation, kept as the type it came in as: a rename edits a name, nothing else."""

LangChainTool = BaseTool | dict[str, Any]
"""What `ModelRequest.tools` holds: a code-side tool, or a provider built-in the model runs itself."""


@dataclass(frozen=True)
class AppliedTools:
    """The tools to advertise, and the two directions a rename has to be translated in."""

    tools: list[LangChainTool]
    """The request's tools in their original order, patched where a published override named one."""
    forward: dict[str, str]
    """Code-side name -> the name it is advertised under, for the tools a published config renamed.

    The direction everything on the way *out* needs: the tool definitions the model is shown, a
    `tool_choice` the code wrote naming one of its own tools, and the calls in the history the model
    is replayed, all have to say the name this request advertises.
    """
    reverse: dict[str, str]
    """Advertised name -> the code-side name, for the tools a published config renamed.

    The direction the model's reply needs, before it becomes anything else: a call translated here
    reaches `ToolNode` under the name the code registered, and is written into the graph's state,
    a checkpoint, and a trace under that name too.
    """


def _parameters(tool: BaseTool) -> dict[str, Any]:
    """The JSON Schema the model is shown for a tool.

    `convert_to_openai_tool` is what LangChain itself binds tools with, so this is the same schema
    the model would have been sent -- with injected and runtime-only arguments already filtered out,
    which a config should neither see in the baseline nor be able to describe.
    """
    function = cast('dict[str, Any]', convert_to_openai_tool(tool)['function'])
    parameters: object = function.get('parameters')
    return cast('dict[str, Any]', parameters) if isinstance(parameters, dict) else {}


def read_tools(tools: Sequence[LangChainTool]) -> list[ToolDef]:
    """The code-side tools a request advertises, as the contract describes them.

    Provider built-ins -- the `dict` entries `create_agent` passes through to a server-side tool
    like web search -- are left out. They have no code-side implementation to route a rename back
    to, and their shape is the provider's, not LangChain's, so there is nothing here to manage.

    LangChain has no notion of a toolset, so no tool reports one and an override that names one
    matches nothing. That is reported, not silently ignored.
    """
    return [
        ToolDef(name=tool.name, description=tool.description or None, parameters_json_schema=_parameters(tool))
        for tool in tools
        if isinstance(tool, BaseTool)
    ]


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
    definitions = read_tools(tools)
    applied = apply_tool_definitions(definitions, config, on_unmatched=on_unmatched)

    result: list[LangChainTool] = []
    index = 0
    for tool in tools:
        if not isinstance(tool, BaseTool):
            result.append(tool)
            continue
        code, managed = definitions[index], applied.tools[index]
        index += 1
        if managed == code:
            # Nothing published named this tool. Advertising the object the agent built keeps a
            # request with no overrides for it identical to the one the agent would have sent.
            result.append(tool)
            continue
        result.append(
            tool.model_copy(
                update={
                    'name': managed.name,
                    # `None` is "this override said nothing about the description", which is not the
                    # same as an override that deliberately says nothing: an empty code-side
                    # description is a choice, and falling back on truthiness would undo it.
                    'description': tool.description if managed.description is None else managed.description,
                    # A JSON Schema `dict` is one of the two shapes `args_schema` takes, and the
                    # copy drops the tool's cached conversions, so this is the schema the model is
                    # shown. It never reaches validation: the copy is only ever advertised.
                    'args_schema': managed.parameters_json_schema,
                }
            )
        )
    # LangChain advertises every tool into one namespace and has no toolsets, so the core's keys are
    # all `(None, name)` and a bare name is an identity. Only the renames are kept: every other tool
    # already answers to the name it is advertised under, in both directions.
    return AppliedTools(
        tools=result,
        forward={name: advertised for (_, name), advertised in applied.forward.items() if advertised != name},
        reverse={advertised: name for (_, advertised), name in applied.reverse.items() if advertised != name},
    )


def rename_tool_choice(tool_choice: Any, names: Mapping[str, str]) -> Any:
    """A `tool_choice` naming one of the code's tools, saying the name this request advertises.

    A forced tool choice is a decision the code made about its own tools, so it has to survive an
    overlay that renames one of them: left alone, it names a tool the model is no longer shown and
    the provider rejects the request. Both spellings the integrations take are translated -- the bare
    name, and the dict OpenAI and Anthropic each wrap it in -- and anything else is passed through,
    including the `'auto'`/`'any'`/`'none'` words, which are not tool names.
    """
    # Read through a second name, so what falls through is handed back as it came in rather than
    # as whatever an `isinstance` narrowed it to.
    choice: object = tool_choice
    if isinstance(choice, str):
        return names.get(choice, choice)
    if isinstance(choice, dict):
        entries = cast('dict[str, Any]', choice)
        function: object = entries.get('function')
        if isinstance(function, dict):
            named = cast('dict[str, Any]', function)
            name: object = named.get('name')
            if isinstance(name, str) and name in names:
                return {**entries, 'function': {**named, 'name': names[name]}}
        name = entries.get('name')
        if isinstance(name, str) and name in names:
            return {**entries, 'name': names[name]}
    return tool_choice


def _rename_call(call: dict[str, Any], names: Mapping[str, str]) -> dict[str, Any]:
    name: object = call.get('name')
    return {**call, 'name': names[name]} if isinstance(name, str) and name in names else call


def _rename_message(message: MessageT, names: Mapping[str, str]) -> MessageT:
    """One message, with every call it makes to a renamed tool saying the other name."""
    if not isinstance(message, AIMessage):
        return message
    updates: dict[str, Any] = {}
    tool_calls = [_rename_call(cast('dict[str, Any]', call), names) for call in message.tool_calls]
    if any(new is not old for new, old in zip(tool_calls, message.tool_calls)):
        updates['tool_calls'] = tool_calls
    if isinstance(message.content, list):
        # Anthropic prefers `tool_calls` when a content block shares its id, but the blocks are what
        # a provider is replayed when it does not, so the name is translated in both places.
        content = [
            _rename_call(cast('dict[str, Any]', entry), names)
            if isinstance(entry, dict) and entry.get('type') in ('tool_use', 'tool_call')
            else entry
            for entry in message.content
        ]
        if any(new is not old for new, old in zip(content, message.content)):
            updates['content'] = content
    return message.model_copy(update=updates) if updates else message


def rename_tool_calls(messages: Sequence[MessageT], names: Mapping[str, str]) -> list[MessageT]:
    """Every call in a conversation, saying the names of the side it is about to be read by.

    Used in both directions with the mapping for that direction: forward over the history a request
    replays, so the model sees the names it was shown; back over the model's reply, so the graph
    dispatches, stores, and traces the names the code gave its tools. A message that calls nothing
    renamed is the object that came in, so nothing else about the conversation is rewritten.
    """
    return [_rename_message(message, names) for message in messages]
