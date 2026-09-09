"""The pure half of Agent Control: what a published `AgentConfig` does to an agent's request.

Everything here takes plain data in and gives plain data back -- no Logfire, no network, no
framework. An adapter enumerates what its framework is about to send, hands it to these functions
along with the resolved config, and sends back what they return. That is the whole contract, and it
is why an adapter is a hook plus twenty lines rather than a reimplementation of these semantics.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, TypeAlias

from pydantic import ValidationError

from ._config import (
    SETTING_ADAPTERS,
    AgentConfig,
    AgentConfigSettings,
    InstructionBlock,
    InstructionText,
    ParameterOverride,
    ToolDefinitionOverride,
    ToolKey,
    describe_tool_key,
    first_by_key,
    instruction_blocks,
)
from ._reporting import OnUnmatched, UnappliedEntry, report_unapplied, report_unmatched, warn_dropped
from ._schema import MAX_MODEL_FACING_TEXT_LENGTH
from ._units import MAX_TIMEOUT_SECONDS, is_representable_timeout


@dataclass(frozen=True)
class Block:
    """One instruction block an agent is about to send, as the adapter sees it.

    The neutral shape of "part of a prompt": some text, the `id` a published config addresses it by,
    and whether the framework recomputes it per request. Frameworks that assemble their prompt from
    several sources map each source to a block; frameworks with one prompt string produce one block
    (`id='agent'` by convention, the only id the contract reserves).
    """

    text: str
    """The block's text, exactly as the model would be shown it."""
    id: str | None = None
    """The key a published entry addresses this block by, or `None` if nothing can address it.

    A block with no `id` is not a defect: an anonymous callable prompt genuinely has nothing stable
    to name it by, and publishing it as unaddressable is how the editor knows not to offer an
    override for it.
    """
    dynamic: bool = False
    """Whether the framework recomputes this block on every request.

    A dynamic block cannot be overridden -- see `apply_instructions` -- and its text never leaves the
    process in a baseline, because it is this request's rendering of whatever the run carried.
    """


@dataclass(frozen=True)
class ToolDef:
    """One tool as the model is shown it, which is the only part Agent Control edits.

    Implementation, argument validation, and the parameter names and types stay code-owned; an
    adapter builds a `ToolDef` from its framework's tool, applies what comes back, and never lets a
    published value near what the tool actually does.
    """

    name: str
    """The tool's code-side name, which is what an override names it by."""
    description: str | None = None
    """The description shown to the model."""
    parameters_json_schema: dict[str, Any] = field(default_factory=dict[str, Any])
    """The tool's JSON Schema, of which only top-level parameter descriptions are ever patched."""
    toolset: str | None = None
    """Where the tool came from -- a toolset id, an MCP server name -- or `None` when the framework
    has no such notion. The baseline reports it so the UI can group a long list; an override that
    sets it is narrowed to that group's tool of this `name`."""


@dataclass(frozen=True)
class AppliedInstructions:
    """What `apply_instructions` returns: the blocks to send, and what reached nothing."""

    blocks: list[Block]
    """The blocks to send, with published text swapped in, removed, or added."""
    unapplied: Sequence[UnappliedEntry]
    """Every published instruction entry this request did not apply; see `UnappliedEntry`.

    Already reported under the caller's `OnUnmatched` policy before it is returned, so this is for an
    adapter that wants to do something *else* with them -- put them on a span, count them -- rather
    than the way they are surfaced.
    """


CollisionScope: TypeAlias = Literal['global', 'toolset']
"""Where two advertised tool names actually collide, which is a property of the framework.

A rename is only safe if the core can tell whether the new name is already taken, and "taken" is not
the same question everywhere:

- `'global'` (the default): every tool is advertised into one flat namespace, so any two tools with
  the same advertised name collide. Almost every framework -- OpenAI Agents, LangChain, ADK, LiveKit,
  the AI SDK -- works this way.
- `'toolset'`: the runtime name a tool is advertised under already carries its toolset, as the Claude
  Agent SDK's `mcp__<server>__<tool>` does, so two servers may each advertise a `search`, and
  renaming one of them to `lookup` does not collide with another server's `lookup`.

Getting this wrong is not cosmetic in either direction: too wide drops a legal rename, too narrow
advertises two tools under one name and makes a call unroutable.
"""


@dataclass(frozen=True)
class AppliedTools:
    """What `apply_tool_definitions` returns: the tools to advertise, and where a call comes back to."""

    tools: list[ToolDef]
    """The tools in their original order, with managed names and descriptions applied."""
    routes: dict[str, str]
    """Advertised name -> code-side name, for every advertised tool.

    Total rather than rename-only so a dispatcher can look up any name the model calls without
    special-casing the tools that were not renamed. Frameworks differ on whether the implementation
    should see its old name or the new one, so the mapping is handed over rather than applied here.

    Flat, and therefore exact only under `collision_scope='global'`, where an advertised name
    identifies a tool by itself. An adapter that passes `'toolset'` has said that two toolsets may
    advertise the same name, so it routes through `reverse` instead; this mapping keeps the first of
    such a pair.
    """
    forward: dict[ToolKey, str]
    """`(toolset, code-side name)` -> the name that tool is advertised under.

    The direction an adapter needs on the way *out*: rewriting a `tool_choice`, an `active_tools`
    list, or a replayed history entry that names a tool by the name the code gave it. Keyed on the
    pair rather than the bare name so a framework with toolsets rewrites exactly the one it means.
    """
    reverse: dict[ToolKey, str]
    """`(toolset, advertised name)` -> the tool's code-side name.

    The direction an adapter needs on the way *in*: a call arrives under an advertised name, and
    under `collision_scope='toolset'` the adapter also knows which toolset it came from, which is
    what keeps two servers' identically named tools distinguishable.
    """
    unapplied: Sequence[UnappliedEntry]
    """Every published tool entry, or part of one, this request did not apply; see `UnappliedEntry`.

    Already reported under the caller's `OnUnmatched` policy before it is returned.
    """


def _oversized(text: str) -> bool:
    """Whether text exceeds the per-request budget, counted the way both cores agree to count it.

    In Unicode code points, which is what `len` is here and what `[...text].length` is in JavaScript
    -- deliberately not JavaScript's `String.length`, which counts UTF-16 units and would give an
    emoji or a CJK extension character twice the weight of the same text in Python, so the same
    published value would fit one core's budget and not the other's.
    """
    return len(text) > MAX_MODEL_FACING_TEXT_LENGTH


def _oversized_entry(text: str, *, instruction_id: str | None = None) -> UnappliedEntry:
    """One entry whose text is past the budget, refused rather than truncated."""
    where = f'for instruction block {instruction_id!r} ' if instruction_id is not None else ''
    return UnappliedEntry(
        reason='oversized-text',
        instruction_id=instruction_id,
        message=(
            f'Managed agent config publishes instruction text {where}of {len(text)} characters, past the '
            f'{MAX_MODEL_FACING_TEXT_LENGTH}-character limit on what one managed entry may add to every model '
            'request; that entry is not applied.'
        ),
    )


def apply_instructions(
    blocks: Sequence[Block], config: AgentConfig, *, on_unmatched: OnUnmatched = 'warn'
) -> AppliedInstructions:
    """Apply the `instructions` section to the blocks an agent is about to send.

    An entry with an `id` replaces that block's text, or removes the block when its text is `None`.
    An entry with no `id` adds a block. Order and `dynamic` flags of untouched blocks never change,
    and a replaced block keeps both: frameworks group static text ahead of per-request text so a
    provider can cache the stable prefix, so re-ordering or re-flagging a block on the way through
    would move that cache boundary on every request in exchange for nothing.

    Added blocks land at the end of the leading run of static blocks -- after the last static block
    the agent assembles, before the first dynamic one. That is where a managed addition is both last
    in the prompt as written and still inside the cacheable prefix; appending it after per-request
    text would put published text in the volatile tail instead.

    A dynamic block is deliberately not addressable. Its text is recomputed per request from whatever
    the run carries, so replacing it pins one rendering forever and dropping it removes the
    computation -- either way the block stops doing the thing it was written to do, and nothing about
    the managed value says which. Addressing one is refused and reported rather than applied.

    Three decisions are reported under `on_unmatched` and returned as
    [`UnappliedEntry`][logfire.agent_control.UnappliedEntry]s: an `id` no block carries
    (`'unknown-id'`), an `id` only a dynamic block carries (`'dynamic-id'`), and text past the
    contract's per-request budget (`'oversized-text'`). The first is decided per request, because the
    blocks are this request's: an agent whose prompt varies with its input can carry a block on one
    request and not the next.
    """
    entries = instruction_blocks(config)
    overrides = first_by_key(
        [(entry.id, entry.instructions) for entry in entries if entry.id is not None],
        lambda key: f'instruction id {key!r}',
    )
    added = [entry.instructions for entry in entries if entry.id is None and entry.instructions is not None]
    if not overrides and not added:
        return AppliedInstructions(blocks=list(blocks), unapplied=())

    unapplied: list[UnappliedEntry] = []
    matched: set[str] = set()
    result: list[Block] = []
    for block in blocks:
        if block.id is None or block.id not in overrides:
            result.append(block)
            continue
        # Addressed, and refused for a reason of its own: it is reported as the dynamic case and not
        # again as a key nothing carries.
        matched.add(block.id)
        if block.dynamic:
            unapplied.append(
                UnappliedEntry(
                    reason='dynamic-id',
                    instruction_id=block.id,
                    message=(
                        f'Managed agent config addresses instruction block {block.id!r}, which the agent '
                        'recomputes per request; a managed value would pin or remove that computation, so it is '
                        'not applied and the block keeps what the code produces.'
                    ),
                )
            )
            result.append(block)
            continue
        replacement = overrides[block.id]
        if replacement is None:
            continue
        if _oversized(replacement):
            unapplied.append(_oversized_entry(replacement, instruction_id=block.id))
            result.append(block)
            continue
        result.append(replace(block, text=replacement))
    for key in overrides:
        if key not in matched:
            unapplied.append(
                UnappliedEntry(
                    reason='unknown-id',
                    instruction_id=key,
                    message=(
                        f'Managed agent config addresses instruction block {key!r}, which this request does not '
                        'assemble; that entry applies to nothing.'
                    ),
                )
            )

    additions: list[str] = []
    for text in added:
        if _oversized(text):
            unapplied.append(_oversized_entry(text))
        else:
            additions.append(text)
    if additions:
        boundary = next((index for index, block in enumerate(result) if block.dynamic), len(result))
        result[boundary:boundary] = [Block(text=text) for text in additions]
    return AppliedInstructions(blocks=result, unapplied=report_unapplied(on_unmatched, unapplied))


def _parameter_entry(
    reason: Literal['unknown-parameter', 'no-patchable-schema'], tool: ToolDef, parameter: str, because: str
) -> UnappliedEntry:
    return UnappliedEntry(
        reason=reason,
        toolset=tool.toolset,
        tool=tool.name,
        parameter=parameter,
        message=(
            f'Managed agent config patches parameter {parameter!r} of {describe_tool_key((tool.toolset, tool.name))}, '
            f'which {because}; that patch applies to nothing.'
        ),
    )


def _with_parameters(
    tool: ToolDef, parameters: Mapping[str, ParameterOverride]
) -> tuple[dict[str, Any], list[UnappliedEntry]]:
    """Patch top-level parameter descriptions while preserving all schema structure.

    Reports each patch that reached nothing, which is the half that used to be silent: from the
    Logfire UI, a patch naming a parameter the tool does not have looked exactly like one that
    applied.
    """
    parameters_json_schema = tool.parameters_json_schema
    unapplied: list[UnappliedEntry] = []
    properties = parameters_json_schema.get('properties')
    if not isinstance(properties, dict):
        for name in parameters:
            unapplied.append(_parameter_entry('no-patchable-schema', tool, name, 'has no top-level parameters'))
        return parameters_json_schema, unapplied
    typed_properties: dict[str, Any] = parameters_json_schema['properties']
    new_properties: dict[str, Any] = {}
    changed = False
    for name, schema in typed_properties.items():
        override = parameters.get(name)
        if override is not None and override.description is not None and isinstance(schema, dict):
            parameter_schema: dict[str, Any] = typed_properties[name]
            new_properties[name] = {**parameter_schema, 'description': override.description}
            changed = True
        else:
            new_properties[name] = schema
    for name, override in parameters.items():
        if name not in typed_properties:
            unapplied.append(_parameter_entry('unknown-parameter', tool, name, 'has no parameter of that name'))
        elif override.description is not None and not isinstance(typed_properties[name], dict):
            unapplied.append(
                _parameter_entry('no-patchable-schema', tool, name, 'describes that parameter with no schema object')
            )
    if not changed:
        return parameters_json_schema, unapplied
    return {**parameters_json_schema, 'properties': new_properties}, unapplied


def _apply_override(tool: ToolDef, override: ToolDefinitionOverride) -> tuple[ToolDef, list[UnappliedEntry]]:
    """Apply the LLM-facing parts of an override, returning the original definition for a no-op."""
    changes: dict[str, Any] = {}
    unapplied: list[UnappliedEntry] = []
    if override.new_name is not None and override.new_name != tool.name:
        changes['name'] = override.new_name
    if override.description is not None and override.description != tool.description:
        changes['description'] = override.description
    if override.parameters:
        schema, unapplied = _with_parameters(tool, override.parameters)
        if schema is not tool.parameters_json_schema:
            changes['parameters_json_schema'] = schema
    return (replace(tool, **changes) if changes else tool), unapplied


def _namespace(tool: ToolDef, scope: CollisionScope) -> str | None:
    """The set of advertised names this tool competes in; see `CollisionScope`."""
    return tool.toolset if scope == 'toolset' else None


def apply_tool_definitions(
    tools: Sequence[ToolDef],
    config: AgentConfig,
    *,
    on_unmatched: OnUnmatched = 'warn',
    reserved: Collection[str] = (),
    collision_scope: CollisionScope = 'global',
) -> AppliedTools:
    """Apply the `tool_definitions` section to the tools an agent is about to advertise.

    An override is matched on the tool's code-side `name`, narrowed to one group when it sets
    `toolset` too. An override narrowed to a group beats one that only names the tool, so a config can
    say "every `search`" and "the CRM's `search`" at once and the specific entry wins where both
    apply. The unqualified entry is then outranked, not unmatched: it still reached the tool it named,
    so only an entry that matched no tool at all is reported. That is decided per call, because tool
    availability is dynamic -- an agent can advertise different tools from one step to the next -- and
    a report from one listing is a report about that listing.

    A rename onto a name that is already taken is dropped while that override's other patches still
    apply, so every tool keeps a name the model can call. What counts as taken is `collision_scope`
    plus `reserved`, and renames resolve in input order, so the tool that was there first keeps the
    name.

    Parameter descriptions are patched in place and every other piece of schema structure is
    preserved. A patch on a parameter the tool does not have, or on one whose schema is not an object
    to patch a description into, applies nothing -- a parameter is part of the tool's code-defined
    shape, and the baseline is what says which ones exist -- and is reported rather than dropped in
    silence.

    Args:
        tools: The tools the agent is about to advertise, in the order it would advertise them.
        config: The resolved managed config.
        on_unmatched: What to do with an entry that reached nothing. Every decision this function
            makes goes through it, a dropped rename included.
        reserved: Advertised names this adapter needs kept free -- an OpenAI Agents handoff, a
            provider-side tool the framework adds after this call, anything outside the editable
            list. A rename onto one of them is refused like any other collision. Read as taken in
            every namespace, which is exact for a framework with one and deliberately conservative
            for a framework with several.
        collision_scope: Where two advertised names collide; see
            [`CollisionScope`][logfire.agent_control.CollisionScope].

    Returns:
        The tools to advertise and the routing maps for them; see
        [`AppliedTools`][logfire.agent_control.AppliedTools].
    """
    overrides = first_by_key(
        [((override.toolset, override.name), override) for override in config.tool_definitions or []],
        describe_tool_key,
    )
    reserved_names = frozenset(reserved)
    # A namespace is the set of advertised names that compete: one for the whole request, or one per
    # toolset. Every code-side name starts out taken, so a rename onto a tool later in the list is a
    # collision rather than a name that is free until that tool is reached.
    taken: dict[str | None, set[str]] = {}
    for tool in tools:
        taken.setdefault(_namespace(tool, collision_scope), set()).add(tool.name)

    unapplied: list[UnappliedEntry] = []
    matched: set[ToolKey] = set()
    applied: list[ToolDef] = []
    routes: dict[str, str] = {}
    forward: dict[ToolKey, str] = {}
    reverse: dict[ToolKey, str] = {}
    for tool in tools:
        qualified: ToolKey = (tool.toolset, tool.name)
        unqualified: ToolKey = (None, tool.name)
        matched.update(key for key in (qualified, unqualified) if key in overrides)
        override = overrides.get(qualified, overrides.get(unqualified))
        if override is None:
            new_tool = tool
        else:
            new_tool, parameter_entries = _apply_override(tool, override)
            unapplied.extend(parameter_entries)
        names = taken[_namespace(tool, collision_scope)]
        if new_tool.name != tool.name and (new_tool.name in names or new_tool.name in reserved_names):
            unapplied.append(
                UnappliedEntry(
                    reason='rename-collision',
                    toolset=tool.toolset,
                    tool=tool.name,
                    message=(
                        f'Managed tool definition override renames {tool.name!r} to {new_tool.name!r}, which is '
                        f'already advertised by another tool; keeping the original name {tool.name!r}.'
                    ),
                )
            )
            new_tool = replace(new_tool, name=tool.name)
        else:
            names.add(new_tool.name)
        applied.append(new_tool)
        routes.setdefault(new_tool.name, tool.name)
        forward[qualified] = new_tool.name
        reverse[(tool.toolset, new_tool.name)] = tool.name
    for key in overrides:
        if key not in matched:
            unapplied.append(
                UnappliedEntry(
                    reason='unknown-tool',
                    toolset=key[0],
                    tool=key[1],
                    message=(
                        f'Managed agent config patches {describe_tool_key(key)}, which no toolset advertises for '
                        'this request; that override applies to nothing.'
                    ),
                )
            )
    return AppliedTools(
        tools=applied,
        routes=routes,
        forward=forward,
        reverse=reverse,
        unapplied=report_unapplied(on_unmatched, unapplied),
    )


def _unrepresentable_timeout_message(timeout: float) -> str:
    return (
        f'Managed agent config sets a request timeout of {timeout!r} seconds, which is not a budget a request can '
        f'be given -- it has to be finite, not negative, and no larger than {MAX_TIMEOUT_SECONDS} seconds; that key '
        'is not applied.'
    )


def apply_settings(
    config: AgentConfig, *, supported: Collection[str] | None = None, on_unmatched: OnUnmatched = 'warn'
) -> dict[str, Any]:
    """The `settings` section as a patch to merge over the agent's own settings.

    Only explicitly set, non-`None` fields are emitted, and every key is already a canonical
    `AgentConfigSettings` name, so the result is the patch: merge it over the framework's settings,
    let a per-call setting outrank it, and leave every key it does not mention alone.
    [`merge_settings`][logfire.agent_control.merge_settings] is how to do that merge with the
    contract's precedence and a record of which layer won each key.

    Three kinds of published key are reported under `on_unmatched` rather than silently dropped, all
    for the same reason -- someone published a setting and the agent did not apply it, which is a gap
    between what Logfire shows and what the agent does:

    - a key this version of the contract has no field for, which a newer Logfire UI can write;
    - a key this adapter cannot lower into its framework, which it names by passing the canonical
      keys it *can* apply as `supported`. Leaving `supported` as `None` says the adapter applies all
      of them;
    - a `timeout` that is not a representable request budget -- negative, not finite, or past
      [`MAX_TIMEOUT_SECONDS`][logfire.agent_control.MAX_TIMEOUT_SECONDS]. Dropped rather than clamped,
      because clamping turns "no real limit" into a deadline nobody published, and rounding a
      negative one to `0` cancels the request before it is sent.
    """
    settings = config.settings
    if settings is None:
        return {}
    for name in settings.unrecognized:
        report_unmatched(
            on_unmatched,
            f'Managed agent config sets {name!r}, which this version of the Agent Control contract has no '
            'model setting for; that key is not applied.',
        )
    values: dict[str, Any] = settings.model_dump(exclude_none=True)
    timeout = values.get('timeout')
    if timeout is not None and not is_representable_timeout(timeout):
        del values['timeout']
        report_unmatched(on_unmatched, _unrepresentable_timeout_message(timeout))
    if supported is None:
        return values
    applied: dict[str, Any] = {}
    for name, value in values.items():
        if name in supported:
            applied[name] = value
        else:
            report_unmatched(
                on_unmatched,
                f'Managed agent config sets {name!r}, which this agent framework has no equivalent for; '
                'that key is not applied.',
            )
    return applied


def canonical_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """A framework's own settings reduced to the contract's canonical keys and describable values.

    What a baseline may say about the code side, and nothing more. Two filters, and both are
    load-bearing rather than tidiness:

    - **Keys.** A framework's settings also carry provider-specific ones and `extra_headers` /
      `extra_body` -- exactly where authorization headers and signed bodies live -- and a baseline is
      published to a variable every member of the Logfire project can read.
    - **Values.** A value the contract has a key for but cannot hold is left out and warned about,
      never approximated. A reasoning effort a framework spells `'max'` is not `'xhigh'`, and
      publishing it as one describes the code as doing something it does not do, in the one artifact
      the Logfire editor presents as the truth about the code. A timeout outside the representable
      range goes the same way.

    Values are read leniently, deliberately unlike a published value: these come from a framework's
    own objects rather than from JSON, so an `int` where the contract wants a `float` and a tuple of
    stop sequences both describe the agent perfectly well, while the same shapes arriving over the
    wire would be a UI writing something the stored schema says it may not.
    """
    canonical: dict[str, Any] = {}
    for name, value in settings.items():
        adapter = SETTING_ADAPTERS.get(name)
        if value is None or adapter is None:
            continue
        if name == 'timeout' and isinstance(value, (int, float)) and not is_representable_timeout(value):
            warn_dropped(
                f'The agent runs with a request timeout of {value!r} seconds, which the Agent Control contract '
                f'cannot describe -- it has to be finite, not negative, and no larger than {MAX_TIMEOUT_SECONDS} '
                'seconds; leaving it out of the published baseline.'
            )
            continue
        try:
            canonical[name] = adapter.validate_python(value)
        except ValidationError:
            warn_dropped(
                f'The agent runs with {name}={value!r}, which the Agent Control contract cannot describe; '
                'leaving it out of the published baseline.'
            )
    return canonical


def _baseline_parameters(tool: ToolDef) -> dict[str, ParameterOverride]:
    """Every top-level parameter the editor may describe, documented in code or not."""
    properties = tool.parameters_json_schema.get('properties')
    if not isinstance(properties, dict):
        return {}
    typed_properties: dict[str, Any] = tool.parameters_json_schema['properties']
    parameters: dict[str, ParameterOverride] = {}
    for name in typed_properties:
        description: Any = None
        if isinstance(typed_properties[name], dict):
            parameter_schema: dict[str, Any] = typed_properties[name]
            description = parameter_schema.get('description')
        parameters[name] = ParameterOverride(description=description if isinstance(description, str) else None)
    return parameters


def build_baseline(
    *,
    instructions: Sequence[Block] = (),
    model: str | None = None,
    settings: Mapping[str, Any] | None = None,
    tools: Sequence[ToolDef] = (),
) -> AgentConfig:
    """Describe the agent as written: what it does with Agent Control removed.

    This is what an adapter publishes as the variable's `example`, and the Logfire editor renders it
    as the code baseline to diff managed values against. It uses the same fields as a published value
    to say *what exists* rather than *what to change*, which it can because an `example` is
    documentation: nothing ever resolves or applies it. The whole contract -- what a baseline is, and
    what each section of one owes the editor -- is in this package's README under "What a baseline
    is"; this is the part of it a framework-neutral function can enforce.

    Instructions are listed block by block, each with the `id` that addresses it and a `dynamic` flag,
    which is the whole reason the UI can offer an override at all: a joined prompt has no seams in it,
    so a baseline built from that could only be copied wholesale -- and since managed instructions
    *add*, that is how you get the agent's own text sent to the model twice with a frozen
    `Today is <date>` in the middle of it.

    A dynamic block contributes that it exists, not what it said once. Its text is one request's
    rendering, built from whatever that request carried -- a tenant name, a user id, a retrieved
    document -- and the baseline is published to a variable every project member can read. The seam is
    what the editor needs anyway: enough to show the block and that it is not theirs to change. A
    dynamic block with nothing to key it on is left out entirely, since an editor can neither show nor
    address it.

    Every top-level parameter of every tool is listed, carrying its `description` when the code has
    one and an empty entry when it does not. The empty entry is the point: an undocumented parameter
    is exactly the one somebody wants to describe from Logfire, and a baseline that listed only the
    documented ones would hide it from the editor until it had been documented in code first.

    Settings pass through [`canonical_settings`][logfire.agent_control.canonical_settings], which
    keeps the baseline to the canonical keys and to values the contract can actually hold.
    """
    entries: list[InstructionText | InstructionBlock] = []
    for block in instructions:
        if block.dynamic:
            if block.id is not None:
                entries.append(InstructionBlock(id=block.id, dynamic=True))
            continue
        if block.text.strip():
            entries.append(InstructionBlock(id=block.id, instructions=block.text, dynamic=False))
    tool_definitions = [
        ToolDefinitionOverride(
            name=tool.name,
            description=tool.description or None,
            parameters=_baseline_parameters(tool) or None,
            toolset=tool.toolset,
        )
        for tool in tools
    ]
    canonical = canonical_settings(settings) if settings else {}
    return AgentConfig(
        instructions=entries or None,
        model=model,
        settings=AgentConfigSettings(**canonical) if canonical else None,
        tool_definitions=tool_definitions or None,
    )
