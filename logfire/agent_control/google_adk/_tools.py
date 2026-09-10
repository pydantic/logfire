"""Reading and rewriting the tool definitions on one ADK request, and keeping a rename off your code.

A rename has two sides, and this module is careful to keep them apart. The model is shown the managed
name -- in the `FunctionDeclaration`s of `llm_request.config.tools`, in a forced `tool_config`, and in
the calls and responses replayed to it out of `llm_request.contents`. Everything on this side of the
model boundary keeps the name the code gave the tool: `llm_request.tools_dict` is left exactly as ADK
built it, and a call the model makes by the managed name is translated back before ADK dispatches it,
so callbacks, `BaseTool.name`, session events, and a resumed conversation all say what your code says.

Nothing here mutates a `Content` or a `Part` in place. ADK hands request assembly shallow copies of
the session's own events, so a nested field written here would rewrite history that has already
happened; a replacement `Part` written onto the request's copy does not.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, cast

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .. import ToolDef


def declarations(llm_request: LlmRequest) -> Iterator[types.FunctionDeclaration]:
    """Every function declaration this request advertises, in the order the model is shown them.

    A request also carries provider-side tools -- Google Search, code execution, URL context, a
    provider-hosted MCP server -- as members of the same list that hold no declaration. Those are not
    tools the contract describes: the model is not shown a name and a description this adapter could
    patch, and nothing dispatches them back into the agent's code. ADK's own `MCPToolset` is not one
    of them; it resolves to ordinary function declarations, and is managed like any other tool.

    Only `types.Tool` members are read, which is what ADK itself does everywhere it walks this list
    (`_find_tool_with_function_declarations`, and the live-API scan in `base_llm_flow`). Everything
    ADK appends here it appends as a `types.Tool`, and a `GenerateContentConfig` coerces a mapping
    into one on the way in.
    """
    for tool in llm_request.config.tools or []:
        if isinstance(tool, types.Tool):
            yield from tool.function_declarations or []


def _schema(declaration: types.FunctionDeclaration) -> dict[str, Any]:
    """A declaration's parameters as a JSON Schema dictionary, whichever field ADK put them in.

    ADK emits `parameters_json_schema` by default and the older `parameters` (a genai `Schema`) when
    the JSON-schema feature is off or a tool builds its declaration by hand. Both describe the same
    thing, and only the top-level parameter descriptions in it are ever patched.
    """
    json_schema: Any = declaration.parameters_json_schema
    if isinstance(json_schema, dict):
        # Typed `Any` by genai, and a JSON Schema object by every producer ADK has: a tool's schema
        # comes from `pydantic.create_model`, an OpenAPI document, or an MCP server's manifest.
        return cast('dict[str, Any]', json_schema)
    if declaration.parameters is not None:
        return declaration.parameters.model_dump(exclude_none=True, mode='json')
    return {}


def read(llm_request: LlmRequest, toolsets: Mapping[str, str]) -> list[ToolDef]:
    """Describe the tools this request advertises, in the shape the contract's helpers take."""
    return [
        ToolDef(
            name=declaration.name or '',
            description=declaration.description,
            parameters_json_schema=_schema(declaration),
            toolset=toolsets.get(declaration.name or ''),
        )
        for declaration in declarations(llm_request)
    ]


def write(llm_request: LlmRequest, tools: Sequence[ToolDef]) -> None:
    """Put the applied definitions back on the request, for the model and for the model alone.

    The declarations are patched in place and in order. That is ADK's own idiom rather than a
    liberty: a tool hands assembly a fresh copy of its declaration for exactly this reason, and ADK
    renames one in place itself when a toolset carries a `tool_name_prefix`.

    `tools_dict` is deliberately not touched. It is what ADK dispatches a returning call through, and
    what a `before_tool_callback` is handed its tool out of, so re-keying it would make a rename in
    Logfire change what the agent's own code sees. The call is translated back by `to_code_names`
    instead.
    """
    for declaration, tool in zip(declarations(llm_request), tools):
        declaration.description = tool.description
        _write_schema(declaration, tool.parameters_json_schema)
        declaration.name = tool.name


def _write_schema(declaration: types.FunctionDeclaration, schema: Mapping[str, Any]) -> None:
    """Patch the parameter descriptions the contract's helper produced back into the declaration.

    Only descriptions are written, and only onto parameters the declaration already has: the schema
    that came back is the tool's own with descriptions swapped, and everything else in it -- names,
    types, requiredness, nested structure -- is code-defined and stays exactly as ADK built it.
    """
    if isinstance(declaration.parameters_json_schema, dict):
        # What came back is this tool's own schema with descriptions swapped and every other piece of
        # structure preserved, so the whole thing goes back rather than a walk over its parameters.
        declaration.parameters_json_schema = dict(schema)
        return
    if declaration.parameters is None:
        return
    # The older shape is a genai `Schema`, which `_schema` read by dumping it. Only the descriptions
    # come back out of that dump, onto the parameters the declaration itself declares.
    described: dict[str, Any] = schema.get('properties') or {}
    for name, parameter in (declaration.parameters.properties or {}).items():
        description = described.get(name, {}).get('description')
        if isinstance(description, str):
            parameter.description = description


def renames(routes: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """The two directions a rename is needed in, out of the core's advertised -> code routing.

    `forward` is code -> advertised, for everything the model is about to be shown; `reverse` is
    advertised -> code, for the call that comes back. Only the tools an override actually renamed are
    in either, so an unmanaged request maps nothing and walks no history at all.
    """
    forward = {code: advertised for advertised, code in routes.items() if advertised != code}
    return forward, {advertised: code for code, advertised in forward.items()}


def _renamed_part(part: types.Part, names: Mapping[str, str]) -> types.Part:
    """One part with the tool it names translated, or the part itself when it names none."""
    call = part.function_call
    if call is not None and (renamed := names.get(call.name or '')) is not None:
        return part.model_copy(update={'function_call': call.model_copy(update={'name': renamed})})
    response = part.function_response
    if response is not None and (renamed := names.get(response.name or '')) is not None:
        return part.model_copy(update={'function_response': response.model_copy(update={'name': renamed})})
    return part


def _renamed_content(content: types.Content, names: Mapping[str, str]) -> types.Content:
    """One content with every tool it names translated, or the content itself when nothing changed."""
    parts = content.parts or []
    renamed = [_renamed_part(part, names) for part in parts]
    if all(new is old for new, old in zip(renamed, parts)):
        return content
    return content.model_copy(update={'parts': renamed})


def advertise(llm_request: LlmRequest, names: Mapping[str, str]) -> None:
    """Say the managed name everywhere else in this request where the model is told a tool's name.

    Two places besides the declarations. The conversation replayed in `contents` holds the calls and
    responses of earlier turns under the names the *code* gives them, because that is what this
    adapter persists; translating them forward is what keeps a transcript consistent with the tool
    list beside it -- across a rename that has changed since an earlier turn, and across one that was
    withdrawn entirely. And `tool_config.function_calling_config.allowed_function_names` is the
    agent's own choice of which tools this request may call, written in code names, which has to go
    on meaning that after an overlay renames one of them.
    """
    if not names:
        return
    contents = llm_request.contents
    for index, content in enumerate(contents):
        renamed = _renamed_content(content, names)
        if renamed is not content:
            contents[index] = renamed
    _advertise_tool_choice(llm_request.config, names)


def _advertise_tool_choice(config: types.GenerateContentConfig, names: Mapping[str, str]) -> None:
    """Rewrite a forced tool selection, onto copies: ADK shares `tool_config` with the agent itself."""
    tool_config = config.tool_config
    calling = tool_config.function_calling_config if tool_config is not None else None
    allowed = calling.allowed_function_names if calling is not None else None
    if tool_config is None or calling is None or not allowed:
        return
    renamed = [names.get(name, name) for name in allowed]
    if renamed == list(allowed):
        return
    config.tool_config = tool_config.model_copy(
        update={'function_calling_config': calling.model_copy(update={'allowed_function_names': renamed})}
    )


def to_code_names(llm_response: LlmResponse, names: Mapping[str, str]) -> None:
    """Put the code's own name back on every call the model made, before ADK dispatches it.

    This is the whole of what keeps a rename model-facing. ADK looks a returning call up in
    `tools_dict` by name, writes that name into the session event it persists, and hands the tool it
    found to `before_tool_callback` -- so translating ahead of all three is what lets a name-keyed
    callback, an approval rule, or a conversation resumed after the rename changed go on matching the
    name the code wrote.
    """
    content = llm_response.content
    if not names or content is None:
        return
    renamed = _renamed_content(content, names)
    if renamed is not content:
        llm_response.content = renamed
