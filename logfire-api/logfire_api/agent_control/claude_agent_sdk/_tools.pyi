from claude_agent_sdk import AgentDefinition as AgentDefinition, ClaudeAgentOptions, HookMatcher as HookMatcher, SdkMcpTool
from claude_agent_sdk.types import McpSdkServerConfig, McpServerConfig as McpServerConfig
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from logfire.agent_control import Resolution as Resolution, ToolDef as ToolDef, ToolKey as ToolKey
from typing import Any

@dataclass(frozen=True)
class _Registered:
    """What it takes to rebuild an in-process server: the version and tools it was built from."""
    version: str
    tools: tuple[SdkMcpTool[Any], ...]

def sdk_mcp_server(name: str, version: str = '1.0.0', tools: list[SdkMcpTool[Any]] | None = None) -> McpSdkServerConfig:
    """Build an in-process MCP server whose tool definitions stay editable from Logfire.

    A drop-in replacement for `claude_agent_sdk.create_sdk_mcp_server` with the same arguments and the
    same return value. The difference is bookkeeping: `create_sdk_mcp_server` freezes each tool's
    name, description, and schema into the server and keeps no reference to the definitions it was
    given, so a managed description would have nothing to rewrite. This remembers them.

    Tools in a server built with `create_sdk_mcp_server` still work exactly as written; they are
    simply not listed in the baseline and not editable.
    """
def tool_definitions(options: ClaudeAgentOptions) -> list[ToolDef]:
    """The tools of `options` whose definitions Agent Control can read and rewrite.

    Each tool's `toolset` is its server name, which is both how the Logfire UI groups a long list and
    how an override tells two servers' `search` tools apart. The name is the code-side one; the model
    is shown `mcp__<server>__<name>`.
    """
def model_facing_name(server: str, tool: str) -> str:
    """What the model calls an in-process tool: the name every permission rule is keyed on."""
def rebuild_servers(options: ClaudeAgentOptions, code_tools: list[ToolDef], managed_tools: list[ToolDef]) -> dict[str, McpServerConfig] | None:
    """Rebuild each in-process server whose tools were patched.

    `managed_tools` is what `apply_tool_definitions` returned for `code_tools`, in the same order, so
    the two zip. A server with no patched tool is left as the exact object the caller built, and a
    patched server keeps every unpatched tool as its original definition -- rewriting only what a
    published value actually changed, so nothing else about the wire format can drift.

    Returns the new `mcp_servers` mapping, or `None` when nothing changed.
    """

@dataclass(frozen=True)
class ToolNames:
    """What a published rename did to the names the model calls, in both directions.

    Everything that refers to an in-process tool from outside its own definition -- a permission
    rule, a hook matcher, a subagent's tool list, the name a `can_use_tool` or hook callback is
    handed -- is keyed on `mcp__<server>__<tool>`, the name the *model* calls. A rename that stopped
    at the definition would leave every one of those pointing at a tool that no longer answers to
    that name, so the two directions are what the rest of this module rewrites with:

    - `managed` is the way *out*, for a name the code wrote: a permission rule, a matcher, a
      subagent's `tools` entry, and a rule a permission callback asks to add.
    - `code` is the way *in*, for a name the CLI hands back: the `tool_name` a callback is called
      with, and the permission suggestions that come with it.
    """
    managed: Mapping[str, str]
    code: Mapping[str, str]
    def __bool__(self) -> bool:
        """Whether anything was renamed at all."""

def tool_names(forward: Mapping[ToolKey, str]) -> ToolNames:
    """The model-facing renames behind `apply_tool_definitions`'s `(toolset, name) -> advertised` map.

    Built from the core's own mapping rather than re-derived by comparing definitions, so what the
    permissions, the matchers, and the callbacks are rewritten with is the same decision the tool
    list was rewritten with -- collisions the core refused included.
    """
def rename_permissions(entries: Sequence[str], renames: Mapping[str, str]) -> list[str]:
    """Rewrite `allowed_tools` / `disallowed_tools` entries that name a renamed tool.

    Permissions are keyed on the name the *model* calls, so a rename that did not reach them would
    silently un-allow a tool the user allowed. An entry may carry a specifier -- `Bash(rm *)` -- which
    is kept as written around the rewritten name.
    """
def managed_references(options: ClaudeAgentOptions, names: ToolNames, resolution: Resolution) -> tuple[dict[str, Any], list[str]]:
    """Everything on `options` that names a tool, rewritten around a rename.

    Returns the `ClaudeAgentOptions` changes and the messages the caller reports under its
    `on_unmatched` policy. The callbacks are wrapped whether or not anything was renamed: the
    wrapper is also what puts the resolved config's label and version on the spans a hook or a
    permission check emits, which is the only place this adapter gets to re-enter that scope once the
    options it built have been handed to a session it does not run.
    """
