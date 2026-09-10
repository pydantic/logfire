from .. import ToolDef as ToolDef
from collections.abc import Iterator, Mapping, Sequence
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

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
def read(llm_request: LlmRequest, toolsets: Mapping[str, str]) -> list[ToolDef]:
    """Describe the tools this request advertises, in the shape the contract's helpers take."""
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
def renames(routes: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """The two directions a rename is needed in, out of the core's advertised -> code routing.

    `forward` is code -> advertised, for everything the model is about to be shown; `reverse` is
    advertised -> code, for the call that comes back. Only the tools an override actually renamed are
    in either, so an unmanaged request maps nothing and walks no history at all.
    """
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
def to_code_names(llm_response: LlmResponse, names: Mapping[str, str]) -> None:
    """Put the code's own name back on every call the model made, before ADK dispatches it.

    This is the whole of what keeps a rename model-facing. ADK looks a returning call up in
    `tools_dict` by name, writes that name into the session event it persists, and hands the tool it
    found to `before_tool_callback` -- so translating ahead of all three is what lets a name-keyed
    callback, an approval rule, or a conversation resumed after the rename changed go on matching the
    name the code wrote.
    """
