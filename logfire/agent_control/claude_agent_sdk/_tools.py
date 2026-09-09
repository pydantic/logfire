"""The one tool surface Agent Control can reach in this SDK: in-process (SDK MCP) tools.

The Claude Agent SDK does not build model requests -- it spawns the `claude` CLI and talks JSON over
stdio, and the tool list the model is shown is assembled inside that process. Built-in tools (`Read`,
`Bash`, ...) and external MCP servers are therefore sealed: their descriptions live in the CLI binary
or behind the CLI's own MCP client, and nothing the SDK passes can re-describe them.

In-process servers are the exception, because the SDK serves them itself: it holds an
`mcp.server.Server` and answers `tools/list` from definitions captured when the server was built. So
a managed name or description is applied by *rebuilding the server* from rewritten tool definitions
before a session starts -- which is why this module ships its own `sdk_mcp_server`, whose only job is
to remember the tools each server was built from so they can be rewritten later.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from weakref import WeakKeyDictionary

from claude_agent_sdk import (
    AgentDefinition,
    CanUseTool,
    ClaudeAgentOptions,
    HookCallback,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    PermissionResult,
    PermissionResultAllow,
    PermissionUpdate,
    SdkMcpTool,
    ToolPermissionContext,
    _build_input_schema,  # type: ignore[reportPrivateUsage]
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import HookEvent, McpSdkServerConfig, McpServerConfig

from logfire.agent_control import Resolution, ToolDef, ToolKey


@dataclass(frozen=True)
class _Registered:
    """What it takes to rebuild an in-process server: the version and tools it was built from."""

    version: str
    tools: tuple[SdkMcpTool[Any], ...]


_REGISTERED: MutableMapping[Any, _Registered] = WeakKeyDictionary()
"""Servers built through `sdk_mcp_server`, keyed on the `mcp.server.Server` the SDK will serve.

Keyed on the instance rather than on the server name because the name is the caller's, reused across
processes and test runs, while the instance is the exact object a given `ClaudeAgentOptions` points
at. Weak so a server built for one session does not outlive it.

The registration cannot live on the config dict itself: for an in-process server the SDK JSON-encodes
every key except `instance` into the CLI's `--mcp-config` argument, so an extra key would either leak
into the command line or fail to serialize.
"""


def sdk_mcp_server(name: str, version: str = '1.0.0', tools: list[SdkMcpTool[Any]] | None = None) -> McpSdkServerConfig:
    """Build an in-process MCP server whose tool definitions stay editable from Logfire.

    A drop-in replacement for `claude_agent_sdk.create_sdk_mcp_server` with the same arguments and the
    same return value. The difference is bookkeeping: `create_sdk_mcp_server` freezes each tool's
    name, description, and schema into the server and keeps no reference to the definitions it was
    given, so a managed description would have nothing to rewrite. This remembers them.

    Tools in a server built with `create_sdk_mcp_server` still work exactly as written; they are
    simply not listed in the baseline and not editable.
    """
    config = create_sdk_mcp_server(name, version, tools)
    _REGISTERED[config['instance']] = _Registered(version=version, tools=tuple(tools or ()))
    return config


def _servers(options: ClaudeAgentOptions) -> dict[str, tuple[McpSdkServerConfig, _Registered]]:
    """The in-process servers of `options` this adapter can rewrite, in the order they were declared.

    Order is preserved because it becomes the order the model is shown the tools in, which is part of
    the prompt-cache prefix; rebuilding a server must not move it.
    """
    configs = options.mcp_servers
    if not isinstance(configs, dict):
        # `mcp_servers` may also be a path to an MCP config file, which names external servers only.
        return {}
    found: dict[str, tuple[McpSdkServerConfig, _Registered]] = {}
    typed_configs: dict[str, McpServerConfig] = configs
    for name, config in typed_configs.items():
        if config.get('type') != 'sdk':
            continue
        sdk_config: McpSdkServerConfig = config  # type: ignore[assignment]
        registered = _REGISTERED.get(sdk_config['instance'])
        if registered is not None:
            found[name] = (sdk_config, registered)
    return found


def tool_definitions(options: ClaudeAgentOptions) -> list[ToolDef]:
    """The tools of `options` whose definitions Agent Control can read and rewrite.

    Each tool's `toolset` is its server name, which is both how the Logfire UI groups a long list and
    how an override tells two servers' `search` tools apart. The name is the code-side one; the model
    is shown `mcp__<server>__<name>`.
    """
    return [
        ToolDef(
            name=tool.name,
            description=tool.description,
            parameters_json_schema=_build_input_schema(tool),
            toolset=server,
        )
        for server, (_, registered) in _servers(options).items()
        for tool in registered.tools
    ]


def model_facing_name(server: str, tool: str) -> str:
    """What the model calls an in-process tool: the name every permission rule is keyed on."""
    return f'mcp__{server}__{tool}'


def rebuild_servers(
    options: ClaudeAgentOptions, code_tools: list[ToolDef], managed_tools: list[ToolDef]
) -> dict[str, McpServerConfig] | None:
    """Rebuild each in-process server whose tools were patched.

    `managed_tools` is what `apply_tool_definitions` returned for `code_tools`, in the same order, so
    the two zip. A server with no patched tool is left as the exact object the caller built, and a
    patched server keeps every unpatched tool as its original definition -- rewriting only what a
    published value actually changed, so nothing else about the wire format can drift.

    Returns the new `mcp_servers` mapping, or `None` when nothing changed.
    """
    patches: dict[str, dict[str, ToolDef]] = {}
    for code_tool, managed_tool in zip(code_tools, managed_tools):
        if managed_tool != code_tool:
            assert code_tool.toolset is not None  # Every tool this adapter enumerates names its server.
            patches.setdefault(code_tool.toolset, {})[code_tool.name] = managed_tool
    if not patches:
        return None

    servers: dict[str, McpServerConfig] = dict(options.mcp_servers)  # type: ignore[arg-type]
    for server, (_, registered) in _servers(options).items():
        per_tool = patches.get(server)
        if per_tool is None:
            continue
        rebuilt: list[SdkMcpTool[Any]] = []
        for tool in registered.tools:
            managed_tool = per_tool.get(tool.name)
            if managed_tool is None:
                rebuilt.append(tool)
                continue
            rebuilt.append(
                # The handler is carried over untouched, so a renamed tool reaches the same function
                # object: the SDK dispatches on the advertised name and the handler is never told one.
                SdkMcpTool(
                    name=managed_tool.name,
                    description=managed_tool.description or '',
                    input_schema=managed_tool.parameters_json_schema,
                    handler=tool.handler,
                    annotations=tool.annotations,
                )
            )
        servers[server] = sdk_mcp_server(server, registered.version, rebuilt)
    return servers


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
    """Code-side model-facing name -> the name the model is shown."""
    code: Mapping[str, str]
    """The name the model is shown -> the code-side model-facing name."""

    def __bool__(self) -> bool:
        """Whether anything was renamed at all."""
        return bool(self.managed)


def tool_names(forward: Mapping[ToolKey, str]) -> ToolNames:
    """The model-facing renames behind `apply_tool_definitions`'s `(toolset, name) -> advertised` map.

    Built from the core's own mapping rather than re-derived by comparing definitions, so what the
    permissions, the matchers, and the callbacks are rewritten with is the same decision the tool
    list was rewritten with -- collisions the core refused included.
    """
    managed: dict[str, str] = {}
    for (toolset, name), advertised in forward.items():
        assert toolset is not None  # Every tool this adapter enumerates names its server.
        if advertised != name:
            managed[model_facing_name(toolset, name)] = model_facing_name(toolset, advertised)
    return ToolNames(managed=managed, code={new: old for old, new in managed.items()})


def rename_permissions(entries: Sequence[str], renames: Mapping[str, str]) -> list[str]:
    """Rewrite `allowed_tools` / `disallowed_tools` entries that name a renamed tool.

    Permissions are keyed on the name the *model* calls, so a rename that did not reach them would
    silently un-allow a tool the user allowed. An entry may carry a specifier -- `Bash(rm *)` -- which
    is kept as written around the rewritten name.
    """
    renamed: list[str] = []
    for entry in entries:
        name, separator, specifier = entry.partition('(')
        renamed.append(f'{renames.get(name, name)}{separator}{specifier}')
    return renamed


def _renamed_agents(
    agents: Mapping[str, AgentDefinition] | None, names: ToolNames
) -> dict[str, AgentDefinition] | None:
    """Rewrite the tool references in each subagent's own allow and deny lists.

    A subagent's `tools` list is a permission rule like any other, keyed on the name the model calls.
    Left alone, a rename would take a tool the subagent was explicitly allowed straight out of its
    reach -- which is a change to what the agent can do, from an override that only meant to rename.
    """
    if not agents:
        return None
    renamed = {
        key: replace(
            agent,
            tools=agent.tools if agent.tools is None else rename_permissions(agent.tools, names.managed),
            disallowedTools=(
                agent.disallowedTools
                if agent.disallowedTools is None
                else rename_permissions(agent.disallowedTools, names.managed)
            ),
        )
        for key, agent in agents.items()
    }
    return None if renamed == agents else renamed


def _matches(pattern: str, name: str) -> bool:
    """Whether the CLI's regular-expression matcher `pattern` fires for tool `name`.

    A pattern the `re` module cannot compile matches nothing, which is what it already did before any
    rename: an unparseable matcher is the user's own bug, and reporting it as a rename this adapter
    could not preserve would be blaming a published value for it.
    """
    try:
        return re.search(pattern, name) is not None
    except re.error:
        return False


def _unpreservable(event: HookEvent, pattern: str | None, names: ToolNames) -> list[str]:
    """The renames a hook matcher stops firing for, which only the user can decide what to do about.

    Exact names and exact `A|B` alternatives are rewritten. What is left is a matcher written as a
    pattern, and a pattern is not something to edit on a guess -- `mcp__shop__.*` still matches a
    renamed tool, while `mcp__shop__refund.*` no longer does, and nothing about the two says which
    one the author meant. So the ones that visibly stopped matching are reported rather than
    rewritten or passed over: a `PreToolUse` hook that quietly stops running is a permission check
    that quietly stops happening.
    """
    if pattern is None:
        # A matcher of `None` runs for every tool, which a rename cannot change.
        return []
    return [
        f'Managed agent config renames the tool the model calls {old!r} to {new!r}, but the {event} hook matcher '
        f'{pattern!r} matches the old name and not the new one. This adapter rewrites exact names only, since '
        'rewriting a pattern would mean editing a regular expression on a guess; that hook no longer runs for '
        'that tool.'
        for old, new in names.managed.items()
        if _matches(pattern, old) and not _matches(pattern, new)
    ]


def _renamed_matcher(matcher: str | None, names: ToolNames) -> str | None:
    """Rewrite the alternatives of a hook matcher that name a renamed tool exactly."""
    if matcher is None:
        return None
    return '|'.join(names.managed.get(part, part) for part in matcher.split('|'))


def _code_side_input(payload: HookInput, names: ToolNames) -> HookInput:
    """The hook payload with the tool named the way the code that reads it names it."""
    fields: dict[str, Any] = dict(payload)
    code_name = names.code.get(fields.get('tool_name', ''))
    if code_name is None:
        return payload
    return {**fields, 'tool_name': code_name}  # type: ignore[return-value]


def _code_side_hook(hook: HookCallback, names: ToolNames, resolution: Resolution) -> HookCallback:
    """One hook callback, called with the tool's code-side name and inside the resolved config's scope."""

    async def code_side(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
        with resolution.reported():
            return await hook(_code_side_input(payload, names), tool_use_id, context)

    return code_side


def _renamed_update(update: PermissionUpdate, renames: Mapping[str, str]) -> PermissionUpdate:
    """One permission update with the tool names of its rules translated."""
    if update.rules is None:
        return update
    return replace(
        update,
        rules=[replace(rule, tool_name=renames.get(rule.tool_name, rule.tool_name)) for rule in update.rules],
    )


def _code_side_context(context: ToolPermissionContext, names: ToolNames) -> ToolPermissionContext:
    """The permission context with the CLI's suggested rules named the way the code names them."""
    suggestions = [_renamed_update(update, names.code) for update in context.suggestions]
    return context if suggestions == context.suggestions else replace(context, suggestions=suggestions)


def _code_side_can_use_tool(can_use_tool: CanUseTool, names: ToolNames, resolution: Resolution) -> CanUseTool:
    """The permission handler, called with the tool's code-side name and answering in managed ones.

    A handler branching on `tool_name` is the whole point of the callback, so handing it the managed
    name would make a rename change which branch runs -- from an override that only meant to change
    what the model is told. It is therefore called with the name the code gave the tool, and the one
    thing it says back that carries a name -- the permission rules it asks to add -- is translated
    into the model's names again, because those go to the CLI.
    """

    async def code_side(tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext) -> PermissionResult:
        with resolution.reported():
            result = await can_use_tool(
                names.code.get(tool_name, tool_name), tool_input, _code_side_context(context, names)
            )
            if isinstance(result, PermissionResultAllow) and result.updated_permissions is not None:
                return replace(
                    result,
                    updated_permissions=[
                        _renamed_update(update, names.managed) for update in result.updated_permissions
                    ],
                )
            return result

    return code_side


def managed_references(
    options: ClaudeAgentOptions, names: ToolNames, resolution: Resolution
) -> tuple[dict[str, Any], list[str]]:
    """Everything on `options` that names a tool, rewritten around a rename.

    Returns the `ClaudeAgentOptions` changes and the messages the caller reports under its
    `on_unmatched` policy. The callbacks are wrapped whether or not anything was renamed: the
    wrapper is also what puts the resolved config's label and version on the spans a hook or a
    permission check emits, which is the only place this adapter gets to re-enter that scope once the
    options it built have been handed to a session it does not run.
    """
    changes: dict[str, Any] = {}
    unapplied: list[str] = []

    if names:
        # Permissions and subagent tool lists are keyed on the name the model calls, so a rename that
        # stopped at the tool definition would quietly un-allow a tool the user allowed.
        if options.allowed_tools:
            changes['allowed_tools'] = rename_permissions(options.allowed_tools, names.managed)
        if options.disallowed_tools:
            changes['disallowed_tools'] = rename_permissions(options.disallowed_tools, names.managed)
        prompt_tool = options.permission_prompt_tool_name
        if prompt_tool is not None and prompt_tool in names.managed:
            changes['permission_prompt_tool_name'] = names.managed[prompt_tool]
        agents = _renamed_agents(options.agents, names)
        if agents is not None:
            changes['agents'] = agents

    if options.hooks:
        hooks: dict[HookEvent, list[HookMatcher]] = {}
        for event, matchers in options.hooks.items():
            rewritten: list[HookMatcher] = []
            for matcher in matchers:
                pattern = _renamed_matcher(matcher.matcher, names)
                unapplied.extend(_unpreservable(event, pattern, names))
                rewritten.append(
                    replace(
                        matcher,
                        matcher=pattern,
                        hooks=[_code_side_hook(hook, names, resolution) for hook in matcher.hooks],
                    )
                )
            hooks[event] = rewritten
        changes['hooks'] = hooks

    if options.can_use_tool is not None:
        changes['can_use_tool'] = _code_side_can_use_tool(options.can_use_tool, names, resolution)

    return changes, unapplied
