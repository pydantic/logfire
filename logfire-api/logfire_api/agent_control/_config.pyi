from ._reporting import warn_dropped as warn_dropped
from ._schema import MAX_MODEL_FACING_TEXT_LENGTH as MAX_MODEL_FACING_TEXT_LENGTH
from _typeshed import Incomplete
from collections.abc import Callable, Hashable
from pydantic import BaseModel, TypeAdapter
from typing import Any, Literal, TypeAlias, TypeVar

KeyT = TypeVar('KeyT', bound=Hashable)
EntryT = TypeVar('EntryT')

class AgentConfigSettings(BaseModel):
    """Canonical model settings managed as one section of an `AgentConfig`.

    The fields are the contract: the settings every framework Agent Control drives has a knob for,
    under the names Pydantic AI's `ModelSettings` gives them, so a published value lowers into any
    SDK without translation and means the same thing to every reader. Unset fields keep their
    code-defined values. The model itself is the sibling `model` field on `AgentConfig`.

    Nothing else gets through. A key this contract has no field for is dropped rather than forwarded
    -- a key it does not understand is not one it can lower into a request -- and remembered in
    `_unrecognized` so the adapter can report it under its `OnUnmatched` policy, since a newer UI's
    key that an SDK quietly did nothing with is exactly the kind of gap between what Logfire shows
    and what the agent does that has to be visible. A field whose *value* this release doesn't
    recognize -- an effort level a newer contract accepts -- is dropped with a warning so that
    setting alone keeps its code-defined value, rather than failing the enclosing `AgentConfig`.
    """
    model_config: Incomplete
    max_tokens: int | None
    temperature: float | None
    top_p: float | None
    top_k: int | None
    seed: int | None
    presence_penalty: float | None
    frequency_penalty: float | None
    parallel_tool_calls: bool | None
    timeout: float | None
    stop_sequences: list[str] | None
    thinking: bool | Literal['minimal', 'low', 'medium', 'high', 'xhigh'] | None
    @property
    def unrecognized(self) -> tuple[str, ...]:
        """The published keys this contract has no field for, for an adapter to report."""

SETTING_ADAPTERS: dict[str, TypeAdapter[Any]]
NonEmptyStr: TypeAlias
InstructionText: TypeAlias

class InstructionBlock(BaseModel):
    """One entry in `AgentConfig.instructions`: a block to add, or a patch on a block the agent assembles.

    Instructions are the one section that composes rather than replaces, so an entry has to say *which*
    text it means. An entry with no `id` adds a block; an entry with an `id` addresses the instruction
    blocks the agent has already assembled under that key.

    | Entry | Effect |
    |---|---|
    | `'text'` (a bare string in the list) | Adds a block. Shorthand for `InstructionBlock(instructions='text')`. |
    | `InstructionBlock(instructions='text')` | Adds a block. |
    | `InstructionBlock(id=key, instructions='text')` | Replaces the text of every block keyed `key`. |
    | `InstructionBlock(id=key)` | Drops every block keyed `key`. |

    An `id` nothing matches applies nothing and is reported under the adapter's `OnUnmatched` policy,
    exactly like an unknown tool name: one config is applied across deployments that need not all
    assemble the same prompt, so the default is a warning rather than an error. Two entries naming the
    same `id` keep the first, with a warning.
    """
    id: str | None
    instructions: InstructionText | None
    dynamic: bool | None

class ParameterOverride(BaseModel):
    """A patch over one top-level parameter of a tool's LLM-facing definition.

    Only what the model is shown changes. The parameter's name, type, and requiredness stay as
    defined in code, so argument validation is unaffected.
    """
    description: str | None

class ToolDefinitionOverride(BaseModel):
    """A patch over a tool's LLM-facing definition.

    Overrides change only what the model is shown. Schema structure, validation, and execution
    remain code-defined. `name` looks the tool up by its original code-side name, narrowed to one
    toolset's tool of that name when `toolset` is set too. An entry that doesn't validate is dropped
    from `AgentConfig.tool_definitions` with a warning, leaving its siblings in place; two entries
    with the same `name` and `toolset` keep the first, with a warning.
    """
    name: str
    new_name: str | None
    description: str | None
    parameters: dict[str, ParameterOverride] | None
    toolset: str | None

def first_by_key(entries: list[tuple[KeyT, EntryT]], describe: Callable[[KeyT], str]) -> tuple[dict[KeyT, EntryT], list[tuple[KeyT, str]]]:
    """Index entries by key, keeping the first of any duplicates and naming the rest.

    Both list sections address things by key, so both can be written with the same key twice -- by a
    hand-edited value, or by a UI bug. Keeping the first matches how a colliding rename is resolved in
    `apply_tool_definitions`: the request stays predictable and the ignored entry is named, rather than
    the last writer silently winning depending on how the JSON happened to be ordered. `describe`
    renders a key for that message, since a tool's key is a pair and reads badly as a bare tuple.

    Returns the index plus every duplicate key with the message naming it, for the caller to turn into
    a `'duplicate-entry'` issue of its own section. Deliberately not warned from here: this is an
    apply-time decision about a value, so it belongs under the caller's `OnUnmatched` policy like
    every other one -- warning directly, as this used to, meant `'ignore'` still warned and `'error'`
    did not raise.
    """
ToolKey: TypeAlias = tuple[str | None, str]

def describe_tool_key(key: ToolKey) -> str: ...

class AgentConfig(BaseModel):
    """The schema contract shared with the Logfire Agent Control UI.

    Every managed value is a patch on the code-defined agent. A key present in the value is managed
    from Logfire; an absent key keeps code-defined behavior. Removing a key in Logfire is therefore
    a deliberate revert to code.

    Nothing an SDK fails to understand costs more than the part that contains it. Extra keys retain
    Pydantic's default `ignore` behavior, and a *value* it cannot make sense of -- an effort level a
    newer contract accepts, a tool override that doesn't validate -- drops only its own setting or
    its own override, with a warning. Both rules exist for the same reason: a value that fails
    validation falls back through Logfire's resolution to the code-defined agent *in its entirety*,
    so without them one unfamiliar key or enum value would silently un-manage the instructions, the
    model, and every tool override alongside it. An extra key is nonetheless *remembered* and
    reported under the adapter's `OnUnmatched` policy, at both levels: a `settings` key this release
    has no field for, and a top-level key it has no section for. Ignoring what it cannot do is what
    keeps a future section readable by an older SDK; saying so is what stops the first person who
    publishes one from getting a silently degraded agent.
    """
    model_config: Incomplete
    instructions: InstructionText | list[InstructionText | InstructionBlock] | None
    model: NonEmptyStr | None
    settings: AgentConfigSettings | None
    tool_definitions: list[ToolDefinitionOverride] | None
    @property
    def unrecognized(self) -> tuple[str, ...]:
        """The published top-level keys this release has no section for, for an adapter to report."""

def instruction_blocks(config: AgentConfig) -> list[InstructionBlock]:
    """The `instructions` section as blocks, whichever of its two shapes was written."""
