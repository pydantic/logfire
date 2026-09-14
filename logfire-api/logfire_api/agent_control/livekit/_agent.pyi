from .. import AgentConfig as AgentConfig, AgentControl as AgentControl, apply_instructions as apply_instructions, apply_settings as apply_settings, build_baseline as build_baseline, merge_settings as merge_settings
from ._instructions import Modality as Modality, baseline_blocks as baseline_blocks, blocks_for as blocks_for, join as join, render as render
from ._models import build as build, canonical_id as canonical_id
from ._settings import Lowered as Lowered, UNKNOWN as UNKNOWN, carry_settings as carry_settings, code_settings as code_settings, lower as lower, plugin_for as plugin_for
from ._tools import advertise as advertise, forward_names as forward_names, managed_tools as managed_tools, rename_calls as rename_calls, rename_tool_choice as rename_tool_choice, renamed as renamed, tool_def as tool_def, toolset_ids as toolset_ids, toolset_names as toolset_names
from _typeshed import Incomplete
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from livekit.agents import llm
from livekit.agents.types import APIConnectOptions, FlushSentinel as FlushSentinel, NotGivenOr
from livekit.agents.voice import Agent, ModelSettings
from typing import Any

DEFAULT_MODALITY: Modality

def installed_llm(agent: Agent) -> llm.LLM | llm.RealtimeModel | None:
    """The model object this agent's turns run on: its own if it has one, else the session's.

    The rule `AgentActivity.llm` uses, restated on the public properties, because it is both what
    `update_options(llm=...)` moves and what this package puts a `ManagedLLM` in front of.
    """
def effective_llm(agent: Agent) -> llm.LLM | llm.RealtimeModel | None:
    """The model behind whatever this agent is running on, with a managed request boundary removed.

    Every comparison this package makes -- has the user swapped the model, is the published one
    already in place, which plugin's settings table applies -- is about the real model, not about a
    boundary a managed request installed in front of it.
    """
def turn_modality(agent: Agent) -> Modality:
    """Which `Instructions` variant this turn asks for.

    LiveKit re-renders modality-specific instructions per turn, so a managed prompt has to be
    assembled for the same modality: assembling the audio variant for a text turn would quietly hand
    the model an agent's voice guidance in a chat.
    """
def realtime_modality(model: llm.RealtimeModel) -> Modality:
    """Which variant a realtime session renders, which is fixed for the session rather than per turn.

    The rule `AgentActivity._render_realtime_instructions` uses, so the text this package puts back
    when an override is withdrawn is exactly the text the framework itself would have sent.
    """
def manages_anything(config: AgentConfig | None) -> bool:
    """Whether a resolved config asks for anything at all.

    A variable that exists with every section empty says the same thing as no variable: run the agent
    as written, on the model it was built with, with no request boundary in front of it.
    """
async def iterate(node: Any) -> AsyncGenerator[Any, None]:
    """Yield from whatever a custom `llm_node` returned, in each shape LiveKit documents for one.

    A node may be an async iterable, or a coroutine resolving to one, or to a single chunk, a string,
    or nothing at all. The framework normalizes all of those itself, but only once the node has
    returned -- so an adapter that delegates to `super().llm_node()` has to do it too, or a perfectly
    ordinary custom node would break the moment this package entered the process.
    """
def install_instructions(chat_ctx: llm.ChatContext, text: str) -> None:
    """Put `text` in the system message LiveKit reserves for the agent's own instructions.

    The item is replaced rather than edited: the turn's context is a shallow copy of the agent's
    history, so writing to the message in place would rewrite the conversation the agent keeps and
    leave published text in it after the request. A context carrying no such message gets one at the
    front, inside the prefix a provider can cache.
    """

@dataclass
class ManagedRequest:
    """The overlay one model request goes out under.

    Built by `llm_node` from the resolution it opened, and read by `ManagedLLM.chat` -- which is
    where the request the agent's own node assembled actually is, and therefore the only place the
    overlay can be applied without taking that node's turn away from it.
    """
    config: AgentConfig
    control: AgentControl
    toolsets: Mapping[object, str]
    instructions: str | None
    settings: Lowered
    routes: dict[str, str] = field(default_factory=dict[str, str])

class ManagedLLM(llm.LLM):
    """The request boundary a managed turn goes through, in front of the model it really runs on.

    LiveKit's only per-request seam is `Agent.llm_node`, and a managed request needs to change three
    things a node does not pass on -- the tool list, the settings, the connection timeout -- so an
    adapter that applied them by calling `chat()` itself would be taking that hook away from whoever
    wrote one. Instead the overlay lives here, one layer down: the agent's own node runs, assembles
    the request it always did, and this applies the published config to the call it makes.

    Wrapping the model rather than replacing it also keeps the activity's metrics and error handling
    pointed at the real thing, which is why both are forwarded rather than re-derived.
    """
    inner: Incomplete
    def __init__(self, inner: llm.LLM) -> None: ...
    def detach(self) -> None:
        """Stop forwarding the inner model's events, for a boundary no longer in front of it."""
    @property
    def model(self) -> str: ...
    @property
    def provider(self) -> str: ...
    def prewarm(self, *, loop: Any = None) -> None: ...
    async def aclose(self) -> None: ...
    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None, conn_options: APIConnectOptions = ..., parallel_tool_calls: NotGivenOr[bool] = ..., tool_choice: NotGivenOr[llm.ToolChoice] = ..., extra_kwargs: NotGivenOr[dict[str, Any]] = ...) -> llm.LLMStream:
        """Apply the request in flight to the call the agent's node just made.

        What the node passed is what it wants: the tools are the ones it chose to advertise, and a
        `tool_choice`, `parallel_tool_calls` or `extra_kwargs` it set is a value for this one
        request, which the contract puts above a published one. The connection options are the
        session's, forwarded verbatim by every node, so a published `timeout` narrows them.
        """

class ManagedAgent(Agent):
    """The behavior `agent_control` mixes in ahead of the agent's own class.

    Mixed in rather than written into the user's class so that `super()` still reaches their
    `on_enter` and their `llm_node`, and so that an agent no config manages runs exactly the code it
    would have run without this package in the process.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Note the agent as written, before any lifecycle hook has had a chance to change it."""
    async def on_enter(self) -> None:
        """Apply what only a realtime session can be told, and put back what it was last told."""
    async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings) -> AsyncGenerator[llm.ChatChunk | str | FlushSentinel, None]:
        """Resolve the config for this request, put it under the agent's own node, and route back.

        The resolution is held open for the whole request, so every span inside it -- the model
        request, each tool call -- carries the label and version that produced it.
        """
