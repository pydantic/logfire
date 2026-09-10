"""What a managed LiveKit `Agent` does at its hooks.

`Agent.llm_node` is the whole stateless story: it is called once per model request, it is handed the
turn's chat context and the flattened tool list, and it is what calls `LLM.chat()`. So the resolution
is opened there, per request -- but the overlay itself is applied one layer further down, on a model
the agent is swapped onto for the request, so that the agent's *own* `llm_node` still runs whether or
not anything is published. A realtime model never reaches `llm_node` -- its instructions and tools go
out over the session's own update -- so `on_enter` applies what a realtime session can be told,
reconciles what a previous entry installed, and reports the rest.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, AsyncIterable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, ClassVar, cast

from livekit.agents import llm
from livekit.agents.llm.chat_context import Instructions
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, FlushSentinel, NotGivenOr
from livekit.agents.utils.misc import is_given
from livekit.agents.voice import Agent, ModelSettings
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from .. import (
    AgentConfig,
    AgentControl,
    apply_instructions,
    apply_settings,
    build_baseline,
    merge_settings,
)
from ._instructions import Modality, baseline_blocks, blocks_for, join, render
from ._models import build, canonical_id
from ._settings import UNKNOWN, Lowered, carry_settings, code_settings, lower, plugin_for
from ._tools import (
    advertise,
    forward_names,
    managed_tools,
    rename_calls,
    rename_tool_choice,
    renamed,
    tool_def,
    toolset_ids,
    toolset_names,
)

if TYPE_CHECKING:
    from livekit.agents.metrics import LLMMetrics

DEFAULT_MODALITY: Modality = 'audio'
"""What LiveKit renders instructions for when no turn says otherwise, as `update_instructions` does."""

_UNSET: Any = object()
"""What `_agent_control_installed_llm` holds before this agent has installed anything."""


def installed_llm(agent: Agent) -> llm.LLM | llm.RealtimeModel | None:
    """The model object this agent's turns run on: its own if it has one, else the session's.

    The rule `AgentActivity.llm` uses, restated on the public properties, because it is both what
    `update_options(llm=...)` moves and what this package puts a `ManagedLLM` in front of.
    """
    own = agent.llm
    return own if is_given(own) else agent.session.llm


def effective_llm(agent: Agent) -> llm.LLM | llm.RealtimeModel | None:
    """The model behind whatever this agent is running on, with a managed request boundary removed.

    Every comparison this package makes -- has the user swapped the model, is the published one
    already in place, which plugin's settings table applies -- is about the real model, not about a
    boundary a managed request installed in front of it.
    """
    model = installed_llm(agent)
    return model.inner if isinstance(model, ManagedLLM) else model


def turn_modality(agent: Agent) -> Modality:
    """Which `Instructions` variant this turn asks for.

    LiveKit re-renders modality-specific instructions per turn, so a managed prompt has to be
    assembled for the same modality: assembling the audio variant for a text turn would quietly hand
    the model an agent's voice guidance in a chat.
    """
    speech = agent.session.current_speech
    return DEFAULT_MODALITY if speech is None else speech.input_details.modality


def realtime_modality(model: llm.RealtimeModel) -> Modality:
    """Which variant a realtime session renders, which is fixed for the session rather than per turn.

    The rule `AgentActivity._render_realtime_instructions` uses, so the text this package puts back
    when an override is withdrawn is exactly the text the framework itself would have sent.
    """
    return 'audio' if model.capabilities.audio_output else 'text'


def manages_anything(config: AgentConfig | None) -> bool:
    """Whether a resolved config asks for anything at all.

    A variable that exists with every section empty says the same thing as no variable: run the agent
    as written, on the model it was built with, with no request boundary in front of it.
    """
    if config is None:
        return False
    sections = (config.instructions, config.model, config.settings, config.tool_definitions)
    return any(section is not None for section in sections)


async def iterate(node: Any) -> AsyncGenerator[Any, None]:
    """Yield from whatever a custom `llm_node` returned, in each shape LiveKit documents for one.

    A node may be an async iterable, or a coroutine resolving to one, or to a single chunk, a string,
    or nothing at all. The framework normalizes all of those itself, but only once the node has
    returned -- so an adapter that delegates to `super().llm_node()` has to do it too, or a perfectly
    ordinary custom node would break the moment this package entered the process.
    """
    if inspect.isawaitable(node):
        node = await node
    if node is None:
        return
    if isinstance(node, AsyncIterable):
        async for chunk in cast('AsyncIterable[Any]', node):
            yield chunk
        return
    yield node


def install_instructions(chat_ctx: llm.ChatContext, text: str) -> None:
    """Put `text` in the system message LiveKit reserves for the agent's own instructions.

    The item is replaced rather than edited: the turn's context is a shallow copy of the agent's
    history, so writing to the message in place would rewrite the conversation the agent keeps and
    leave published text in it after the request. A context carrying no such message gets one at the
    front, inside the prefix a provider can cache.
    """
    index = chat_ctx.index_by_id(INSTRUCTIONS_MESSAGE_ID)
    if index is None:
        chat_ctx.items.insert(0, llm.ChatMessage(id=INSTRUCTIONS_MESSAGE_ID, role='system', content=[text]))
    else:
        previous = chat_ctx.items[index]
        chat_ctx.items[index] = llm.ChatMessage(
            id=INSTRUCTIONS_MESSAGE_ID, role='system', content=[text], created_at=previous.created_at
        )


@dataclass
class ManagedRequest:
    """The overlay one model request goes out under.

    Built by `llm_node` from the resolution it opened, and read by `ManagedLLM.chat` -- which is
    where the request the agent's own node assembled actually is, and therefore the only place the
    overlay can be applied without taking that node's turn away from it.
    """

    config: AgentConfig
    """The resolved config this request is applying."""
    control: AgentControl
    """The control it was resolved through, for reporting what reaches nothing."""
    toolsets: Mapping[object, str]
    """Which toolset each tool came from, which the flat list `llm_node` receives has lost."""
    instructions: str | None
    """The managed prompt to send, or `None` when the config leaves instructions to code."""
    settings: Lowered
    """The published settings, in the shapes `LLM.chat` takes them in."""
    routes: dict[str, str] = field(default_factory=dict[str, str])
    """Advertised name -> code-side name, filled in once the tools have been advertised.

    `llm_node` reads it while forwarding the model's chunks, which happens strictly after `chat()`
    has been called and so strictly after it has been filled in. A node that answers without calling
    the model leaves it empty, and there is nothing to route.
    """


_REQUEST: ContextVar[ManagedRequest | None] = ContextVar('logfire_agent_control_livekit_request', default=None)
"""The overlay the request running in *this task* goes out under.

Per task rather than one slot on the boundary, because LiveKit does not run one generation at a
time. It starts a preemptive one as soon as it has a transcript it might answer -- on by default --
and cancels it when the transcript moves on, immediately before starting the next; cancellation is
asynchronous, so the cancelled task's cleanup runs after the new task has installed its overlay. One
shared slot means that cleanup clears the live one, and the request that survives goes out with no
managed prompt, no renamed tools and no published settings, looking from the outside exactly like a
managed one.
"""


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

    def __init__(self, inner: llm.LLM) -> None:
        super().__init__()
        self.inner = inner
        """The model the agent actually runs on."""
        self._label = inner.label
        inner.on('metrics_collected', self._forward_metrics)
        inner.on('error', self._forward_error)

    def detach(self) -> None:
        """Stop forwarding the inner model's events, for a boundary no longer in front of it."""
        self.inner.off('metrics_collected', self._forward_metrics)
        self.inner.off('error', self._forward_error)

    def _forward_metrics(self, metrics: LLMMetrics) -> None:
        self.emit('metrics_collected', metrics)

    def _forward_error(self, error: llm.LLMError) -> None:
        self.emit('error', error)

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def provider(self) -> str:
        return self.inner.provider

    def prewarm(self, *, loop: Any = None) -> None:
        self.inner.prewarm(loop=loop)

    async def aclose(self) -> None:
        await self.inner.aclose()

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        """Apply the request in flight to the call the agent's node just made.

        What the node passed is what it wants: the tools are the ones it chose to advertise, and a
        `tool_choice`, `parallel_tool_calls` or `extra_kwargs` it set is a value for this one
        request, which the contract puts above a published one. The connection options are the
        session's, forwarded verbatim by every node, so a published `timeout` narrows them.
        """
        request = _REQUEST.get()
        if request is None:
            return self.inner.chat(
                chat_ctx=chat_ctx,
                tools=tools,
                conn_options=conn_options,
                parallel_tool_calls=parallel_tool_calls,
                tool_choice=tool_choice,
                extra_kwargs=extra_kwargs,
            )

        advertised, applied = advertise(
            tools or [], request.config, request.toolsets, on_unmatched=request.control.on_unmatched
        )
        forward = forward_names(applied)
        request.routes = applied.routes
        if request.instructions is not None:
            install_instructions(chat_ctx, request.instructions)
        rename_calls(chat_ctx, forward)

        settings = request.settings
        if settings.timeout is not None:
            conn_options = replace(conn_options, timeout=settings.timeout)
        merged = {**settings.extra_kwargs, **(extra_kwargs if is_given(extra_kwargs) else {})}
        return self.inner.chat(
            chat_ctx=chat_ctx,
            tools=advertised,
            conn_options=conn_options,
            parallel_tool_calls=parallel_tool_calls if is_given(parallel_tool_calls) else settings.parallel_tool_calls,
            tool_choice=rename_tool_choice(tool_choice, forward),
            extra_kwargs=merged or NOT_GIVEN,
        )


class ManagedAgent(Agent):
    """The behavior `agent_control` mixes in ahead of the agent's own class.

    Mixed in rather than written into the user's class so that `super()` still reaches their
    `on_enter` and their `llm_node`, and so that an agent no config manages runs exactly the code it
    would have run without this package in the process.
    """

    _agent_control: ClassVar[AgentControl]
    """The control this class was bound to; set by `agent_control`."""

    _agent_control_code_instructions: str | Instructions
    """The prompt as written, kept apart from the one the agent is holding.

    A realtime session's instructions are *replaced* to apply a managed prompt, so without this there
    would be nothing left to put back when the override is withdrawn, and re-entering the agent would
    publish the managed text as though the code had said it.
    """
    _agent_control_code_tools: list[llm.Tool | llm.Toolset]
    """The tools as written, kept for the same reason and used to build every clone."""
    _agent_control_code_llm: llm.LLM | llm.RealtimeModel | None = None
    """The model the agent runs on with nothing published, so removing a managed `model` restores it."""
    _agent_control_installed_llm: llm.LLM | llm.RealtimeModel | None = _UNSET
    """The model this package last put under the agent, so a later `update_options(llm=...)` by the
    user is recognizable as theirs rather than overwritten by a stale snapshot."""
    _agent_control_pushed_instructions: str | None = None
    """The last prompt this package pushed to a realtime session, for the same distinction."""
    _agent_control_pushed_tools: list[llm.Tool | llm.Toolset] | None = None
    """The last tool list this package pushed to a realtime session, for the same distinction."""
    _agent_control_built_model: tuple[str, llm.LLM | llm.RealtimeModel | None, llm.LLM | None] | None = None
    """The last model built for a published `model`, and what it was built from, so an unchanged
    config rebuilds nothing -- and a model that could not be built is not attempted again on every
    turn."""
    _agent_control_boundary: ManagedLLM | None = None
    """The request boundary in front of the current model, reused across turns so the events it
    forwards are subscribed once rather than once per request."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Note the agent as written, before any lifecycle hook has had a chance to change it."""
        super().__init__(*args, **kwargs)
        self._agent_control_code_instructions = self.instructions
        self._agent_control_code_tools = self.tools

    async def on_enter(self) -> None:
        """Apply what only a realtime session can be told, and put back what it was last told."""
        model = self._agent_control_code_model()
        if isinstance(model, llm.RealtimeModel):
            self._agent_control_installed_llm = model
            with self._agent_control.resolution() as resolution:
                await self._agent_control_realtime(model, resolution.config)
        await super().on_enter()

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> AsyncGenerator[llm.ChatChunk | str | FlushSentinel, None]:
        """Resolve the config for this request, put it under the agent's own node, and route back.

        The resolution is held open for the whole request, so every span inside it -- the model
        request, each tool call -- carries the label and version that produced it.
        """
        control = self._agent_control
        with control.resolution() as resolution:
            config = resolution.config
            # The code model and the session's tools are only knowable once the agent is running, so
            # the baseline the Logfire editor opens on is published from the first request.
            code_model = self._agent_control_code_model()
            control.publish_baseline(
                self._agent_control_baseline(code_model, tools, self._agent_control_toolsets()), source='code'
            )
            # Reconciled before anything else, and for an unmanaged request too: a config that stops
            # naming a model has to put the code one back, and one that manages nothing has to leave
            # the agent running on exactly what its own code chose, with nothing in front of it.
            request = None
            if manages_anything(config):
                assert config is not None
                model = cast('llm.LLM', self._agent_control_build(config.model) or code_model)
                request = ManagedRequest(
                    config=config,
                    control=control,
                    toolsets=self._agent_control_toolsets(),
                    instructions=self._agent_control_prompt(config),
                    settings=self._agent_control_settings(config, model, code_model),
                )
            else:
                model = cast('llm.LLM', code_model)
            self._agent_control_install(model, managed=request is not None)
            token = _REQUEST.set(request)
            try:
                async for chunk in iterate(super().llm_node(chat_ctx, tools, model_settings)):
                    if request is not None and isinstance(chunk, llm.ChatChunk) and chunk.delta:
                        for call in chunk.delta.tool_calls:
                            # The model answers with the name it was shown. The framework dispatches
                            # on the code name, and the history it writes should read that way too.
                            call.name = request.routes.get(call.name, call.name)
                    yield chunk
            finally:
                _REQUEST.reset(token)

    # -- Keeping the code side and the applied side apart --

    def _agent_control_code_model(self) -> llm.LLM | llm.RealtimeModel | None:
        """The model the agent runs on as written, adopting one the user swapped in themselves.

        Re-read rather than snapshotted once, because `update_options(llm=...)` is a supported thing
        to do mid-session -- but only when what is there is not what this package last installed, so
        a managed model is never mistaken for the code's own choice and promoted into the baseline.
        """
        current = effective_llm(self)
        if current is not self._agent_control_installed_llm:
            self._agent_control_code_llm = current
        return self._agent_control_code_llm

    def _agent_control_code_prompt(self) -> str | Instructions:
        """The prompt as written, adopting one the user replaced with `update_instructions()`."""
        pushed = self._agent_control_pushed_instructions
        if pushed is None or self.instructions != pushed:
            self._agent_control_code_instructions = self.instructions
        return self._agent_control_code_instructions

    def _agent_control_code_tool_list(self) -> list[llm.Tool | llm.Toolset]:
        """The tools as written, adopting a list the user replaced with `update_tools()`."""
        pushed = self._agent_control_pushed_tools
        if pushed is None or self.tools != pushed:
            self._agent_control_code_tools = self.tools
        return self._agent_control_code_tools

    # -- The pieces, one section of the config each --

    def _agent_control_toolsets(self) -> dict[object, str]:
        """Which toolset each tool came from, which the flat list `llm_node` receives has lost."""
        return toolset_ids([*self.session.tools, *self._agent_control_code_tools])

    def _agent_control_baseline(
        self,
        model: llm.LLM | llm.RealtimeModel | None,
        tools: Sequence[llm.Tool],
        toolsets: Mapping[object, str],
    ) -> AgentConfig:
        """The agent as written, for the Logfire editor to diff published values against.

        Built from the code side throughout: the prompt the agent was constructed with rather than
        one a runtime `update_instructions()` or a previous entry left behind, and only the tools a
        published value can actually reach on this path.
        """
        plugin = plugin_for(model) if model is not None else UNKNOWN
        settings = None
        if isinstance(model, llm.LLM):
            # A realtime model's knobs are its own -- voice, turn detection, response length -- and
            # none of them is one of the canonical settings, so it has no baseline to describe.
            timeout = self.session.conn_options.llm_conn_options.timeout
            settings = {**code_settings(model, plugin), 'timeout': timeout}
        return build_baseline(
            instructions=baseline_blocks(self._agent_control_code_instructions),
            model=canonical_id(model, plugin.name) if model is not None else None,
            settings=settings,
            tools=[tool_def(tool, toolsets.get(tool), with_schema=True) for _, tool in managed_tools(tools)],
        )

    def _agent_control_install(self, model: llm.LLM, *, managed: bool) -> None:
        """Put `model` under the agent, behind a request boundary when there is something to apply.

        Swapped through `update_options` rather than by calling `chat()` on a model of our own, so
        the activity keeps collecting metrics and errors from whatever the turn actually ran on --
        and so a custom `llm_node` reaches the managed model the same way the default one does.

        The boundary is one object per model rather than one per request: it is only a pass-through
        that reads the overlay of whichever task is calling it, and subscribing to the inner model's
        events once is the whole reason it is kept.
        """
        target: llm.LLM = model
        if managed:
            boundary = self._agent_control_boundary
            if boundary is None or boundary.inner is not model:
                if boundary is not None:
                    boundary.detach()
                boundary = self._agent_control_boundary = ManagedLLM(model)
            target = boundary
        if installed_llm(self) is not target:
            self.update_options(llm=target)
        self._agent_control_installed_llm = model

    def _agent_control_build(self, model_id: str | None) -> llm.LLM | None:
        """The model a published `model` names, or `None` when it names none or cannot be built here.

        Cached on the code model as well as on the id, because the code model is half of what was
        built: a swap through `update_options(llm=...)` can change the base URL, the credentials and
        the HTTP client the published model reuses without changing the id that named it.
        """
        if model_id is None:
            return None
        code_model = self._agent_control_code_llm
        built = self._agent_control_built_model
        if built is None or built[0] != model_id or built[1] is not code_model:
            try:
                model = build(model_id, code_model)
            except Exception as exc:
                self._agent_control.report_unmatched(
                    f'Managed agent config selects model {model_id!r}, which could not be built for this '
                    f'agent ({exc}); the model in code is used instead.'
                )
                model = None
            built = self._agent_control_built_model = (model_id, code_model, model)
        return built[2]

    def _agent_control_prompt(self, config: AgentConfig) -> str | None:
        """The managed prompt for this turn, or `None` when the config leaves instructions to code.

        Assembled from the prompt the agent is *currently* holding rather than from the code
        snapshot: `update_instructions()` is how a LiveKit agent changes what it says at runtime, and
        a managed value rewrites what is being sent rather than what was written months ago.
        """
        if config.instructions is None:
            return None
        control = self._agent_control
        blocks = blocks_for(self.instructions, turn_modality(self))
        applied = apply_instructions(blocks, config, on_unmatched=control.on_unmatched).blocks
        return join([block.text for block in applied])

    def _agent_control_settings(
        self, config: AgentConfig, model: llm.LLM, code_model: llm.LLM | llm.RealtimeModel | None
    ) -> Lowered:
        """The settings this request goes out with, in the shapes this plugin's `chat()` takes them.

        Code first, published over the top. The code layer is empty while the agent is running on its
        own model -- those settings are already on that plugin -- and carries across only when a
        published `model` replaced it with a fresh instance that would otherwise have dropped them.
        """
        control = self._agent_control
        plugin = plugin_for(model)
        published = apply_settings(config, supported=plugin.supported, on_unmatched=control.on_unmatched)
        code: dict[str, Any] = {}
        if model is not code_model and isinstance(code_model, llm.LLM):
            code, lost = carry_settings(code_model, plugin)
            for message in lost:
                control.report_unmatched(message)
        lowered, collisions = lower(merge_settings(code, published).settings, model, plugin)
        for collision in collisions:
            control.report_unmatched(collision)
        return lowered

    # -- Realtime, where a session is configured once rather than per request --

    async def _agent_control_realtime(self, model: llm.RealtimeModel, config: AgentConfig | None) -> None:
        """Apply what a realtime session can be told, put back what it was last told, report the rest.

        A realtime model is configured once per session rather than per request: instructions and
        tools go out on a `session.update`, and `Agent.update_instructions` / `update_tools` are the
        only doors into it. Everything else -- the model itself, every sampling setting -- is fixed
        for the life of the session, so it is reported rather than half-applied.

        Re-entering the same agent lands here again, which is why every piece starts from the code
        side: a section the config no longer carries is put back rather than left as whatever the
        last entry installed.
        """
        control = self._agent_control
        code_instructions = self._agent_control_code_prompt()
        code_tools = self._agent_control_code_tool_list()
        editable = [tool for tool in code_tools if not isinstance(tool, llm.Toolset)]
        modality = realtime_modality(model)
        control.publish_baseline(self._agent_control_baseline(model, editable, {}), source='code')

        capabilities = model.capabilities
        if config is not None and config.model is not None:
            control.report_unmatched(
                f'Managed agent config selects model {config.model!r}, but a running realtime session '
                'cannot be moved to another model; that section is not applied.'
            )
        if config is not None and config.settings is not None:
            # Nothing in the canonical set reaches a realtime model: they take a response length, a
            # voice, and turn-detection options rather than sampling settings.
            apply_settings(config, supported=(), on_unmatched=control.on_unmatched)

        text = render(code_instructions, modality)
        if config is not None and config.instructions is not None:
            if capabilities.mutable_instructions:
                blocks = blocks_for(code_instructions, modality)
                applied = apply_instructions(blocks, config, on_unmatched=control.on_unmatched).blocks
                text = join([block.text for block in applied])
            else:
                control.report_unmatched(
                    'Managed agent config sets instructions, which this realtime model cannot be told '
                    'mid-session; that section is not applied.'
                )
        if text != render(self.instructions, modality):
            await self.update_instructions(text)
            self._agent_control_pushed_instructions = text

        tools = code_tools
        if config is not None and config.tool_definitions is not None:
            if capabilities.mutable_tools:
                tools = self._agent_control_realtime_tools(code_tools, editable, config)
            else:
                control.report_unmatched(
                    'Managed agent config patches tool definitions, which this realtime model cannot be '
                    'told mid-session; that section is not applied.'
                )
        if tools != self.tools:
            await self.update_tools(tools)
            # What the agent ends up holding, not what was handed over: `update_tools` drops a
            # duplicate id, and it is the result a later entry has to recognize as ours.
            self._agent_control_pushed_tools = self.tools

    def _agent_control_realtime_tools(
        self, code_tools: list[llm.Tool | llm.Toolset], editable: Sequence[llm.Tool], config: AgentConfig
    ) -> list[llm.Tool | llm.Toolset]:
        """The tool list to install in the session, and what installing it costs the code.

        Toolsets are left as they are: rebuilding one means reconstructing a class this package knows
        nothing about, and an MCP toolset's tools do not exist until it is set up. An override aimed
        at one of their tools matches nothing and is reported as such.

        A realtime session dispatches on the name the model was shown, and this list *is* its
        dispatcher, so a rename here cannot be the wire-only rename the stateless path does. The
        implementation still runs, with its arguments validated exactly as before -- but the name
        everything downstream of dispatch sees is the managed one, which is reported rather than
        quietly done.
        """
        control = self._agent_control
        advertised, applied = advertise(
            editable, config, {}, on_unmatched=control.on_unmatched, reserved=toolset_names(code_tools)
        )
        for (_, name), advertised_name in renamed(applied):
            control.report_unmatched(
                f'Managed agent config renames tool {name!r} to {advertised_name!r}. A realtime session '
                'dispatches on the name the model was shown, so your tool runs under the new name: '
                f'`ctx.function_call.name`, name-keyed hooks, and the session history say '
                f'{advertised_name!r} rather than {name!r}.'
            )
        remaining = iter(advertised)
        return [tool if isinstance(tool, llm.Toolset) else next(remaining) for tool in code_tools]
