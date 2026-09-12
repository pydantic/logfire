from ._config import AgentConfig as AgentConfig, AgentConfigSettings as AgentConfigSettings, InstructionBlock as InstructionBlock, InstructionText as InstructionText, ParameterOverride as ParameterOverride, SETTING_ADAPTERS as SETTING_ADAPTERS, ToolDefinitionOverride as ToolDefinitionOverride, ToolKey as ToolKey, describe_tool_key as describe_tool_key, first_by_key as first_by_key, instruction_blocks as instruction_blocks
from ._reporting import ApplyIssue as ApplyIssue, warn_dropped as warn_dropped
from ._schema import MAX_MODEL_FACING_TEXT_LENGTH as MAX_MODEL_FACING_TEXT_LENGTH
from ._support import AgentSupport as AgentSupport, Section as Section
from ._units import MAX_TIMEOUT_SECONDS as MAX_TIMEOUT_SECONDS, is_representable_timeout as is_representable_timeout
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias

@dataclass(frozen=True)
class Block:
    '''One instruction block an agent is about to send, as the adapter sees it.

    The neutral shape of "part of a prompt": some text, the `id` a published config addresses it by,
    and whether the framework recomputes it per request. Frameworks that assemble their prompt from
    several sources map each source to a block; frameworks with one prompt string produce one block
    (`id=\'agent\'` by convention, the only id the contract reserves).
    '''
    text: str
    id: str | None = ...
    dynamic: bool = ...

@dataclass(frozen=True)
class ToolDef:
    """One tool as the model is shown it, which is the only part Agent Control edits.

    Implementation, argument validation, and the parameter names and types stay code-owned; an
    adapter builds a `ToolDef` from its framework's tool, applies what comes back, and never lets a
    published value near what the tool actually does.
    """
    name: str
    description: str | None = ...
    parameters_json_schema: dict[str, Any] = field(default_factory=dict[str, Any])
    toolset: str | None = ...

@dataclass(frozen=True)
class AppliedInstructions:
    """What `apply_instructions` returns: the blocks to send, and what reached nothing."""
    blocks: list[Block]
    issues: Sequence[ApplyIssue]

CollisionScope: TypeAlias

@dataclass(frozen=True)
class AppliedTools:
    """What `apply_tool_definitions` returns: the tools to advertise, and where a call comes back to."""
    tools: list[ToolDef]
    routes: dict[str, str]
    forward: dict[ToolKey, str]
    reverse: dict[ToolKey, str]
    issues: Sequence[ApplyIssue]

def apply_instructions(blocks: Sequence[Block], config: AgentConfig) -> AppliedInstructions:
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

    Four decisions come back as [`ApplyIssue`][logfire.agent_control.ApplyIssue]s on `issues`, and
    are reported by nothing here: an `id` no block carries (`'unknown-id'`), an `id` only a dynamic
    block carries (`'dynamic-id'`), text past the contract's per-request budget
    (`'oversized-text'`), and the second and later entries naming one `id` (`'duplicate-entry'`).
    Pass them to [`AgentControl.report`][logfire.agent_control.AgentControl.report] along with the
    other sections'. The first is decided per request, because the blocks are this request's: an
    agent whose prompt varies with its input can carry a block on one request and not the next.
    """
def apply_tool_definitions(tools: Sequence[ToolDef], config: AgentConfig, *, reserved: Collection[str] = (), collision_scope: CollisionScope = 'global') -> AppliedTools:
    '''Apply the `tool_definitions` section to the tools an agent is about to advertise.

    An override is matched on the tool\'s code-side `name`, narrowed to one group when it sets
    `toolset` too. An override narrowed to a group beats one that only names the tool, so a config can
    say "every `search`" and "the CRM\'s `search`" at once and the specific entry wins where both
    apply. The unqualified entry is then outranked, not unmatched: it still reached the tool it named,
    so only an entry that matched no tool at all is reported. That is decided per call, because tool
    availability is dynamic -- an agent can advertise different tools from one step to the next -- and
    a report from one listing is a report about that listing.

    A rename onto a name that is already taken is dropped while that override\'s other patches still
    apply, so every tool keeps a name the model can call. What counts as taken is `collision_scope`
    plus `reserved`, and renames resolve in input order, so the tool that was there first keeps the
    name.

    Parameter descriptions are patched in place and every other piece of schema structure is
    preserved. A patch on a parameter the tool does not have, or on one whose schema is not an object
    to patch a description into, applies nothing -- a parameter is part of the tool\'s code-defined
    shape, and the baseline is what says which ones exist -- and comes back on `issues` rather than
    being dropped in silence.

    Every decision it makes -- an override no tool matched, a patch on a parameter that is not there,
    a dropped rename, the second entry naming one tool -- comes back as an
    [`ApplyIssue`][logfire.agent_control.ApplyIssue] and is reported by nothing here. Hand them to
    [`AgentControl.report`][logfire.agent_control.AgentControl.report] with the other sections\'.

    Args:
        tools: The tools the agent is about to advertise, in the order it would advertise them.
        config: The resolved managed config.
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
    '''

@dataclass(frozen=True)
class AppliedSettings:
    """What `apply_settings` returns: the patch to merge, and what reached nothing."""
    settings: dict[str, Any]
    issues: Sequence[ApplyIssue]

def apply_settings(config: AgentConfig, *, support: AgentSupport | None = None) -> AppliedSettings:
    '''The `settings` section as a patch to merge over the agent\'s own settings.

    Only explicitly set, non-`None` fields are emitted, and every key is already a canonical
    `AgentConfigSettings` name, so `settings` is the patch: merge it over the framework\'s settings,
    let a per-call setting outrank it, and leave every key it does not mention alone.
    [`merge_settings`][logfire.agent_control.merge_settings] is how to do that merge with the
    contract\'s precedence and a record of which layer won each key.

    Five kinds of published thing come back on `issues` rather than being silently dropped, all for
    the same reason -- someone published something and the agent did not apply it, which is a gap
    between what Logfire shows and what the agent does:

    - a key this version of the contract has no field for (`\'unknown-setting\'`), which a newer
      Logfire UI can write;
    - a key this adapter cannot lower into its framework (`\'unsupported-setting\'`), which it names
      through [`AgentSupport.settings`][logfire.agent_control.AgentSupport.settings]. Leaving
      `support` as `None` says the adapter applies all of them;
    - a `timeout` that is not a representable request budget (`\'unrepresentable-timeout\'`) --
      negative, not finite, or past
      [`MAX_TIMEOUT_SECONDS`][logfire.agent_control.MAX_TIMEOUT_SECONDS]. Dropped rather than
      clamped, because clamping turns "no real limit" into a deadline nobody published, and rounding
      a negative one to `0` cancels the request before it is sent;
    - a top-level key this release has no section for (`\'unknown-section\'`);
    - a section this adapter declared it cannot apply (`\'unsupported-section\'`).

    The last two are about the whole config rather than about settings, and they are here because
    this is the helper every adapter can call with the whole config and its own support declaration,
    whatever hooks its framework gives it: an adapter that never calls
    `apply_instructions` would otherwise have nowhere to learn that an `instructions` section was
    published at an agent that cannot apply one.

    Args:
        config: The resolved managed config.
        support: What this adapter can apply; see
            [`AgentSupport`][logfire.agent_control.AgentSupport]. `None` says it can apply every
            section and every canonical setting, which is the right answer for an adapter that has
            not been taught to declare yet and the wrong one for any that has.
    '''
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
def build_baseline(*, instructions: Sequence[Block] = (), model: str | None = None, settings: Mapping[str, Any] | None = None, tools: Sequence[ToolDef] = ()) -> AgentConfig:
    '''Describe the agent as written: what it does with Agent Control removed.

    This is what an adapter publishes as the variable\'s `example`, and the Logfire editor renders it
    as the code baseline to diff managed values against. It uses the same fields as a published value
    to say *what exists* rather than *what to change*, which it can because an `example` is
    documentation: nothing ever resolves or applies it. The whole contract -- what a baseline is, and
    what each section of one owes the editor -- is in this package\'s README under "What a baseline
    is"; this is the part of it a framework-neutral function can enforce.

    Instructions are listed block by block, each with the `id` that addresses it and a `dynamic` flag,
    which is the whole reason the UI can offer an override at all: a joined prompt has no seams in it,
    so a baseline built from that could only be copied wholesale -- and since managed instructions
    *add*, that is how you get the agent\'s own text sent to the model twice with a frozen
    `Today is <date>` in the middle of it.

    A dynamic block contributes that it exists, not what it said once. Its text is one request\'s
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
    '''
