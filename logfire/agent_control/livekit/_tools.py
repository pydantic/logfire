"""Describing LiveKit tools to Logfire, and advertising the managed version of them to the model.

Three things are LiveKit-specific here. A tool's schema is *derived* -- from the signature and
docstring of a `@function_tool`, or carried whole by a `@function_tool(raw_schema=...)` -- so
patching a parameter description means handing the model a schema LiveKit did not build. Dispatch is
an exact-name lookup in the turn's `ToolContext` (`Unknown function: ...` otherwise), so a renamed
tool is advertised as a clone the model calls. And a clone really is dispatched on the realtime path,
where the session's tool list *is* the executable one -- so a clone carrying a patched schema carries
a bridge back to the tool it was cloned from, rather than wrapping its bare function and losing the
validation and context injection LiveKit would have done.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from livekit.agents import llm
from livekit.agents.llm.tool_context import NamedToolChoice, RawFunctionToolInfo
from livekit.agents.llm.utils import build_legacy_openai_schema, prepare_function_arguments
from livekit.agents.types import NotGivenOr
from livekit.agents.voice import RunContext

from .. import AgentConfig, AppliedTools, OnUnmatched, ToolDef, ToolKey, apply_tool_definitions

NO_RUN_CONTEXT = cast('RunContext[Any]', None)
"""The default for a bridge's context parameter, for a caller that dispatches a tool without one.

`llm.utils.prepare_function_arguments` injects a `RunContext` only when it was handed one, and then
binds the tool's signature -- so a bridge whose context parameter had no default could not be called
at all by `execute_function_call`, which passes none. The annotation stays `RunContext[Any]` because
that is what LiveKit's injection matches on: an optional one is not recognized as a context parameter.
"""


def _parts(tool: llm.FunctionTool[..., Any] | llm.RawFunctionTool[..., Any]) -> tuple[Callable[..., Any], Any]:
    """The wrapped function and bound instance, which are what reconstruct a tool wrapper.

    Private on LiveKit's side and unavoidable: they are the only two inputs `FunctionTool.__init__`
    takes besides the info, `__wrapped__` loses the instance a method tool is bound to, and a clone
    handed to a realtime session really is dispatched.
    """
    return tool._func, tool._instance  # pyright: ignore[reportPrivateUsage]


def toolset_ids(tools: Iterable[llm.Tool | llm.Toolset]) -> dict[object, str]:
    """Map each tool to the id of the toolset it came from, so an override can be narrowed to one group.

    Keyed by the tool object rather than its name because the same name can legitimately appear in two
    toolsets, and because that is what the flat list `llm_node` receives can be looked up by -- the
    flattening the framework does before the hook drops the grouping entirely.
    """
    found: dict[object, str] = {}

    def walk(tools: Iterable[llm.Tool | llm.Toolset], toolset: str | None) -> None:
        for tool in tools:
            if isinstance(tool, llm.Toolset):
                walk(tool.tools, tool.id)
            elif toolset is not None:
                found[tool] = toolset

    walk(tools, None)
    return found


def managed_tools(tools: Sequence[llm.Tool]) -> Iterator[tuple[int, Any]]:
    """The tools Agent Control can edit, with their position in the list the model is shown."""
    for index, tool in enumerate(tools):
        if isinstance(tool, (llm.FunctionTool, llm.RawFunctionTool)):
            yield index, tool


def flatten(tools: Iterable[llm.Tool | llm.Toolset]) -> list[llm.Tool]:
    """The tools in `tools`, with each toolset's own tools spliced in where it stood."""
    flat: list[llm.Tool] = []
    for tool in tools:
        if isinstance(tool, llm.Toolset):
            flat.extend(flatten(tool.tools))
        else:
            flat.append(tool)
    return flat


def toolset_names(tools: Iterable[llm.Tool | llm.Toolset]) -> set[str]:
    """Every name a toolset in `tools` already advertises, which a rename must not take.

    The realtime path's counterpart to `reserved_names`. A realtime session's tool list is replaced
    whole and a `Toolset` in it is carried across exactly as it is, so a rename onto a name one of
    its tools already answers to would hand `update_tools` two tools under one name -- and it keeps
    one of them, silently. On the stateless path the flat list the hook receives already contains
    those tools, and `reserved_names` sees them there.
    """
    inside = flatten([tool for tool in tools if isinstance(tool, llm.Toolset)])
    return reserved_names(inside) | {tool.info.name for _, tool in managed_tools(inside)}


def reserved_names(tools: Sequence[llm.Tool]) -> set[str]:
    """The advertised names a rename must not take: the tools this package cannot edit.

    A `ProviderTool` -- web search, code execution -- is advertised to the model under its own id and
    has no definition of ours to patch, so a rename onto that id would leave two tools answering to
    one name and a call nothing can route.
    """
    return {tool.id for tool in tools if not isinstance(tool, (llm.FunctionTool, llm.RawFunctionTool))}


def tool_def(tool: Any, toolset: str | None, *, with_schema: bool) -> ToolDef:
    """One tool as the model is shown it.

    `with_schema` is a cost, not a detail: building a `@function_tool`'s schema means building a
    pydantic model from its signature, so it is done for the tools a published config actually patches
    rather than for every tool on every turn. A tool nothing patches needs only its name to be routed.
    """
    if isinstance(tool, llm.RawFunctionTool):
        raw_schema: dict[str, Any] = tool.info.raw_schema
        description = raw_schema.get('description')
        parameters: dict[str, Any] = raw_schema.get('parameters', {}) if with_schema else {}
    else:
        description = tool.info.description
        parameters = build_legacy_openai_schema(tool)['function']['parameters'] if with_schema else {}
    return ToolDef(
        name=tool.info.name,
        description=description,
        parameters_json_schema=parameters,
        toolset=toolset,
    )


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

    async def call(raw_arguments: dict[str, Any], ctx: RunContext[Any] = NO_RUN_CONTEXT) -> Any:
        args, kwargs = prepare_function_arguments(fnc=tool, json_arguments=raw_arguments, call_ctx=ctx)
        result = tool(*args, **kwargs)
        # `@function_tool` takes a sync function as readily as an async one, and LiveKit's own
        # dispatcher awaits only what is awaitable. A bridge that always awaited would turn a
        # patched parameter description into a `TypeError` for every synchronous tool.
        return await result if isinstance(result, Awaitable) else result

    # `RawFunctionTool` copies these onto itself, and they are what a log line or a traceback names.
    call.__name__ = call.__qualname__ = name
    return call


def clone(tool: Any, definition: ToolDef, *, schema_patched: bool) -> llm.Tool:
    """A tool that advertises `definition` to the model and otherwise behaves like `tool`.

    A rename or a reworded description is applied on the tool's own kind, so a `@function_tool` keeps
    deriving its schema the way the plugin would have. Patching a *parameter* description cannot: the
    schema is derived from the signature and there is nowhere to put the new text, so that one tool is
    advertised as a raw-schema tool carrying the patched schema, wrapped around the `bridge` that
    keeps its execution identical. That drops the strict-mode schema the OpenAI and Anthropic plugins
    would otherwise send for it -- see the README's known limits.
    """
    if isinstance(tool, llm.RawFunctionTool):
        func, instance = _parts(tool)
        raw_schema: dict[str, Any] = {**tool.info.raw_schema, 'name': definition.name}
        if definition.description is not None:
            raw_schema['description'] = definition.description
        if schema_patched:
            raw_schema['parameters'] = definition.parameters_json_schema
        return llm.RawFunctionTool(func, replace(tool.info, name=definition.name, raw_schema=raw_schema), instance)
    if not schema_patched:
        func, instance = _parts(tool)
        info = replace(tool.info, name=definition.name, description=definition.description)
        return llm.FunctionTool(func, info, instance)
    return llm.RawFunctionTool(
        bridge(tool, definition.name),
        RawFunctionToolInfo(
            name=definition.name,
            raw_schema={
                'name': definition.name,
                'description': definition.description or '',
                'parameters': definition.parameters_json_schema,
            },
            flags=tool.info.flags,
            on_duplicate=tool.info.on_duplicate,
            duplicate_scope=tool.info.duplicate_scope,
        ),
    )


def advertise(
    tools: Sequence[llm.Tool],
    config: AgentConfig,
    toolsets: Mapping[object, str],
    *,
    on_unmatched: OnUnmatched,
    reserved: Collection[str] = (),
) -> tuple[list[llm.Tool], AppliedTools]:
    """The tools to send this turn, and the routing the core worked out for them.

    The list the hook was handed is left alone. LiveKit syncs edits to it back into the turn's
    `ToolContext`, which is what dispatches a call, so renaming in place would rename the tool the
    implementation answers to as well; advertising a separate list keeps the rename on the wire only.

    `reserved` is for names a caller knows about that are not in `tools` -- what a `Toolset` the
    realtime path carries across untouched already advertises -- and is added to the ones read off
    the list itself.
    """
    patched = {override.name for override in config.tool_definitions or ()}
    managed = list(managed_tools(tools))
    definitions = [tool_def(tool, toolsets.get(tool), with_schema=tool.info.name in patched) for _, tool in managed]
    applied = apply_tool_definitions(
        definitions, config, on_unmatched=on_unmatched, reserved=reserved_names(tools) | set(reserved)
    )

    advertised = list(tools)
    for (index, tool), before, after in zip(managed, definitions, applied.tools):
        if after is not before:
            schema_patched = after.parameters_json_schema is not before.parameters_json_schema
            advertised[index] = clone(tool, after, schema_patched=schema_patched)
    return advertised, applied


def forward_names(applied: AppliedTools) -> dict[str, str]:
    """Code-side name -> the name that tool is advertised under, for the tools a config renamed.

    `AppliedTools.forward` is keyed on `(toolset, name)` for a framework where a bare name is not an
    identity. LiveKit's is: dispatch, `tool_choice`, and every history entry name a tool by a bare
    string, and two tools sharing one are already unroutable before Agent Control sees them.
    """
    return {key[1]: advertised for key, advertised in applied.forward.items() if key[1] != advertised}


def renamed(applied: AppliedTools) -> list[tuple[ToolKey, str]]:
    """Every tool a config renamed, as `(toolset, code name)` and the name it is advertised under."""
    return [(key, advertised) for key, advertised in applied.forward.items() if key[1] != advertised]


def rename_calls(chat_ctx: llm.ChatContext, forward: Mapping[str, str]) -> None:
    """Rename past tool calls in the outgoing context to the names the model is being shown.

    Without this a renamed tool contradicts itself: the schema offers `lookup_weather` while the
    history shows the assistant calling `get_weather`, a tool that no longer exists as far as the model
    can tell. Items are replaced rather than mutated -- the turn's context is a shallow copy of the
    stored history, so editing an item in place would rewrite the conversation the agent keeps.
    """
    if not forward:
        return
    for index, item in enumerate(chat_ctx.items):
        if isinstance(item, (llm.FunctionCall, llm.FunctionCallOutput)) and (name := forward.get(item.name)):
            chat_ctx.items[index] = item.model_copy(update={'name': name})


def rename_tool_choice(
    tool_choice: NotGivenOr[llm.ToolChoice], forward: Mapping[str, str]
) -> NotGivenOr[llm.ToolChoice]:
    """Point a forced `tool_choice` at the name the model is being shown for that tool.

    A `tool_choice` naming `get_weather` is a decision the code made about which tool to force, not a
    managed setting -- so it has to survive a rename rather than be silently unforced by one. Left
    exactly as it was when it names no tool (`'auto'`, `'required'`, `'none'`) or names one nothing
    renamed.
    """
    if not isinstance(tool_choice, dict):
        return tool_choice
    advertised = forward.get(tool_choice['function']['name'])
    if advertised is None:
        return tool_choice
    renamed_choice: NamedToolChoice = {'type': tool_choice['type'], 'function': {'name': advertised}}
    return renamed_choice
