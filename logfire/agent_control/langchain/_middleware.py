"""The one middleware: resolve once per run, apply per model request, keep a rename off your side."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional, cast

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse, ToolCallRequest
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Command
from typing_extensions import NotRequired

from logfire import Logfire
from logfire.agent_control import (
    AgentConfig,
    AgentControl,
    OnUnmatched,
    Resolution,
    apply_instructions,
    build_baseline,
    merge_settings,
)

from ._instructions import Instruction, SystemPrompt, assemble_system_prompt, read_system_prompt
from ._models import build_model, read_model_id
from ._settings import carry_settings, lower_settings, read_settings
from ._tools import apply_tools, read_tools, rename_tool_calls, rename_tool_choice

STATE_KEY = 'logfire_agent_control'
"""The state key the run's resolution is carried in; see `AgentControlState`."""

DEFAULT_AGENT_NAME = 'LangGraph'
"""What `create_agent` calls an agent that was not given a `name`, from `graph.compile()`."""


class AgentControlState(AgentState[Any]):
    """The agent state, plus the resolution this run started from.

    The config lives in state rather than on the middleware because a middleware instance is shared
    by every concurrent run of its agent, and the whole point of resolving in `before_agent` is that
    one run applies one version of the config from its first model request to its last -- so every
    span of the run agrees on the version that produced it, and a publish mid-run takes effect on
    the next run rather than halfway through this one. Marked private so it stays out of the agent's
    input and output schemas: it is not something a caller passes in or reads back.
    """

    logfire_agent_control: NotRequired[Annotated[Resolution, PrivateStateAttr]]


@dataclass(frozen=True)
class _AppliedRequest:
    """One model request with the run's config applied, and how to read the reply it comes back with."""

    request: ModelRequest[Any]
    """The request to send: the agent's own, with every section a published config manages."""
    reverse: dict[str, str] = field(default_factory=dict[str, str])
    """Advertised name -> code-side name, for the tools this request advertises renamed."""

    def in_code_names(self, response: ModelResponse[Any]) -> ModelResponse[Any]:
        """The reply, with every call to a renamed tool sent back to the tool the code defined.

        Done here, before the reply is returned to the model node, because everything downstream of
        this point is the user's side of the rename: `ToolNode` resolves a call by name against the
        tools the agent registered, a `wrap_tool_call` in any other middleware is keyed on the name
        the code gave the tool, and whatever the graph writes down -- state, a checkpoint, a trace --
        is what a later run is resumed from. A rename is a thing the model is told, and this is the
        boundary it stops at.
        """
        if not self.reverse:
            return response
        return ModelResponse(
            result=rename_tool_calls(response.result, self.reverse),
            structured_response=response.structured_response,
        )


class AgentControlMiddleware(AgentMiddleware[AgentControlState, Any, Any]):
    """Make a LangChain agent's instructions, model, settings, and tool descriptions editable in Logfire.

    [`agent_control`][logfire.agent_control.langchain.agent_control] is how you build one; this is
    the type it returns, for an annotation or a subclass. Add it to `create_agent(middleware=[...])`,
    **last**, and the agent keeps doing exactly what its code says until someone publishes a value in
    Logfire.

    Last, because `wrap_model_call` handlers compose first-in-list as the outermost layer: the last
    middleware is the innermost one, which is both the only position that sees the request every
    other middleware has finished assembling and the only one whose changes nothing downstream can
    overwrite.

    The agent's `name` is the config's key. It is read off each run, where `create_agent` puts the
    `name` it was given and where the LangChain instrumentation reads the name it puts on the agent's
    spans -- so the config lines up with the agent you are already looking at, including when a run's
    own `metadata` renames it, which renames it in both places for that run and no other. An agent
    built without a name has none to key on -- `create_agent` calls it `'LangGraph'` -- and that is
    an error rather than a guess. Pass `name=` here for a key no run can move.
    """

    state_schema = AgentControlState
    """Registers the private channel the run's resolved config rides in; see `AgentControlState`."""

    def __init__(
        self,
        *,
        name: str | None = None,
        instructions: Mapping[str, Instruction] | None = None,
        label: str | None = None,
        logfire_instance: Logfire | None = None,
        on_unmatched: OnUnmatched = 'warn',
        publish_baseline: bool = True,
    ) -> None:
        """Configure how this agent's managed config is read and published.

        Args:
            name: The agent's name, which its config is keyed on as the Logfire variable
                `agent__<name>`. Defaults to the `name` the run says the agent has, which is the one
                that already identifies it in Logfire; pass it here for a key no run can move.
            instructions: The agent's prompt, block by block, instead of `create_agent`'s
                `system_prompt`. Each key is the block's id and each value is its text, or a callable
                taking the `ModelRequest` for a block this request works out for itself. Declaring
                the prompt here is what makes its blocks code-side: they are published with their
                text and can be replaced or removed from Logfire one at a time, while text this
                middleware merely finds on a request cannot be told from a rendering of one run.
            label: The label to resolve, such as `'production'`. When `None`, the variable's own
                targeting rules and rollout choose which label this process gets.
            logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
                global one that `logfire.configure()` sets up.
            on_unmatched: What to do about a published entry that reaches nothing in this
                deployment -- an instruction id this agent's prompt does not carry, an override
                naming a tool it does not advertise, a setting this model has no knob for.
                `'warn'` (the default) says so once per process, `'error'` fails the request, and
                `'ignore'` says nothing.
            publish_baseline: Whether to publish what the agent sends to Logfire, which is what the
                editor diffs published values against and what creates the variable the first time.
                Disable it when the Logfire token is intentionally read-only.
        """
        self.tools = []
        self._name = name
        self._instructions = instructions
        self._label = label
        self._logfire_instance = logfire_instance
        self._on_unmatched: OnUnmatched = on_unmatched
        self._publish_baseline = publish_baseline
        self._control = self._build_control(name) if name is not None else None
        # One control per agent name this middleware has been run as, since a name read off the run
        # is not a property of the middleware; see `_control_for`. `self._control` is the one an
        # explicit `name=` fixed, or else the last one a run established, which is what a request
        # that never went through `before_agent` has to fall back on.
        self._controls: dict[str, AgentControl] = {}
        self._published: set[str] = set()
        # The model the agent itself brings to a request, learned from the first request that has
        # one and never changed after: it is what says whether a *later* request arrived with a
        # model something else chose for it, which a published `model` must not overwrite. Written
        # at most once with a value every request agrees on, so two concurrent runs racing here
        # write the same string; a run whose model was chosen dynamically before this middleware
        # ever ran is the case this cannot see, and is why the baseline says it was observed.
        self._code_model_id: str | None = None

    def __repr__(self) -> str:
        name = self._control.name if self._control is not None else self._name
        return f'{type(self).__name__}(name={name!r}, label={self._label!r})'

    def _build_control(self, name: str) -> AgentControl:
        return AgentControl(
            name,
            label=self._label,
            logfire_instance=self._logfire_instance,
            on_unmatched=self._on_unmatched,
            publish_baseline=self._publish_baseline,
        )

    def _control_for(self, config: RunnableConfig | None) -> AgentControl:
        """The control for the agent this run is of: the one `name=` fixed, or the run's own.

        Read from the run every time rather than remembered from the first one, because the run's
        metadata is the caller's: `agent.invoke(..., {'metadata': {'lc_agent_name': ...}})` overrides
        what `create_agent` bound, and it renames the agent in Logfire's traces too. The config
        keying on the same value is the point -- it lines up with the agent you are already looking
        at -- so a run that renames the agent moves both, and only for itself. Remembering the first
        name would let one run's rename outlive it and point every later run at that config.

        Pass `agent_control(name=...)` to key the config on a name no run can move.
        """
        if self._name is not None:
            return self._require_control()
        metadata: dict[str, Any] = (config or {}).get('metadata') or {}
        name = metadata.get('lc_agent_name')
        if isinstance(name, str) and name and name != DEFAULT_AGENT_NAME:
            # Assigned rather than memoized under a lock: two concurrent runs of one agent build the
            # same control for the same variable, and either is the one to keep.
            control = self._controls.get(name)
            if control is None:
                control = self._controls[name] = self._build_control(name)
            self._control = control
        return self._require_control()

    def _require_control(self) -> AgentControl:
        """The control for the agent last run, or the reason there cannot be one."""
        if self._control is None:
            raise ValueError(
                'Agent Control needs the name of the agent it manages, and this agent has none: '
                f'`create_agent()` was called without `name=`, so LangChain calls it {DEFAULT_AGENT_NAME!r}. '
                'Pass `name=` to `create_agent()` -- it is what Logfire shows the agent as in traces, so '
                'the config lines up with the agent you already see there -- or, if the agent must stay '
                'unnamed, pass `agent_control(name=...)`.'
            )
        return self._control

    def before_agent(
        self,
        state: AgentControlState,
        runtime: Runtime[Any],
        # Spelled `Optional[...]` and defaulted, both deliberately: LangGraph injects the run's
        # config only into a parameter annotated with one of the four spellings it matches on
        # (and warns about any other), and the default is what keeps this a compatible override
        # of a hook the framework also calls with two arguments.
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> dict[str, Any]:
        """Read the published config once, and carry it through every request of this run.

        The run's `config` is asked for by name, which is how LangGraph injects it into a node, and
        it is the only place a middleware can see what the agent is called: `create_agent` puts the
        `name` it was given on every run as `lc_agent_name`, the same value Logfire's LangChain
        instrumentation names the agent's spans with. The compiled graph is not handed to a
        middleware, and `langgraph.config.get_config()` is unavailable to a sync hook running under
        an async invocation on Python 3.10.
        """
        control = self._control_for(config)
        # Entered and left here rather than held: the resolution's telemetry context is what puts
        # the label and version on spans, and a graph node cannot hold a context open across the
        # nodes that come after it. `Resolution.reported` puts it back around each request instead.
        with control.resolution() as resolution:
            return {STATE_KEY: resolution}

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        """Apply the run's config to the request the model is about to be sent."""
        resolution = self._resolution(request.state)
        with resolution.reported():
            applied = self._apply(request, resolution)
            return applied.in_code_names(handler(applied.request))

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]]
    ) -> ModelResponse[Any]:
        """Apply the run's config to the request the model is about to be sent."""
        resolution = self._resolution(request.state)
        with resolution.reported():
            applied = self._apply(request, resolution)
            return applied.in_code_names(await handler(applied.request))

    def wrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]]
    ) -> ToolMessage | Command[Any]:
        """Run a tool call inside the version of the config that asked for it.

        The call itself is passed straight through: it already names the code's tool, because the
        model's reply was translated back before it ever reached the graph. Defining this hook is not
        only for the telemetry, though -- `create_agent` skips its "unknown client-side tool" check
        for an agent whose middleware wraps tool calls, which is what lets a request advertise a tool
        under a name `ToolNode` does not hold.
        """
        with self._resolution(request.state).reported():
            return handler(request)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]
    ) -> ToolMessage | Command[Any]:
        """Run a tool call inside the version of the config that asked for it."""
        with self._resolution(request.state).reported():
            return await handler(request)

    def _resolution(self, state: Any) -> Resolution:
        """The resolution this run started from, or one read now if the run never went through `before_agent`."""
        carried = cast('dict[str, Any]', state)
        if STATE_KEY in carried:
            return cast(Resolution, carried[STATE_KEY])
        with self._require_control().resolution() as resolution:
            return resolution

    def _apply(self, request: ModelRequest[Any], resolution: Resolution) -> _AppliedRequest:
        """The request to send, and what to translate in the reply it comes back with."""
        prompt = self._prompt(request)
        model_id = read_model_id(request.model)
        if self._code_model_id is None:
            self._code_model_id = model_id
        self._publish(request, prompt, model_id)

        config = resolution.config
        if config is None:
            # Nothing published: the agent runs exactly as written, except that a block `id` is a
            # label for Agent Control and not a field any provider should be sent.
            if prompt.must_render:
                return _AppliedRequest(request.override(system_message=prompt.render(prompt.blocks)))
            return _AppliedRequest(request)

        overrides: dict[str, Any] = {}
        blocks = apply_instructions(prompt.blocks, config, on_unmatched=self._on_unmatched).blocks
        if blocks != prompt.blocks or prompt.must_render:
            overrides['system_message'] = prompt.render(blocks)

        applied = apply_tools(request.tools, config, on_unmatched=self._on_unmatched)
        if any(new is not code for new, code in zip(applied.tools, request.tools)):
            overrides['tools'] = applied.tools
        if applied.forward:
            # Everything the model is about to read has to use the names it is being shown: the
            # calls in the conversation it is replayed -- which this side has been keeping under the
            # code's names, and which a resumed thread carries across a change to the rename -- and a
            # `tool_choice` the code wrote naming one of its own tools.
            overrides['messages'] = rename_tool_calls(request.messages, applied.forward)
            tool_choice = rename_tool_choice(request.tool_choice, applied.forward)
            if tool_choice is not request.tool_choice:
                overrides['tool_choice'] = tool_choice

        model = self._model(model_id, config)
        code_settings: dict[str, Any] = {}
        if model is not None:
            overrides['model'] = model
            # A published model is a fresh instance carrying its class's defaults, so the settings
            # the agent's own model was constructed with would silently go away with it. They are
            # the code side of the same contract, so they carry over as the layer a published
            # `settings` section then overrides.
            code_settings = carry_settings(request.model, model)
        has_tools = bool(applied.tools) or request.response_format is not None
        published = lower_settings(model or request.model, config, has_tools=has_tools, on_unmatched=self._on_unmatched)
        # The contract's order, and `model_settings` is the run: it is where another middleware puts
        # a per-call choice for this one request, and where Anthropic prompt-cache directives arrive.
        settings = merge_settings(code_settings, published, request.model_settings).settings
        if settings != request.model_settings:
            overrides['model_settings'] = settings

        return _AppliedRequest(request=request.override(**overrides) if overrides else request, reverse=applied.reverse)

    def _prompt(self, request: ModelRequest[Any]) -> SystemPrompt:
        """The agent's instructions: the ones declared here, or the ones this request carries.

        The two are alternatives rather than layers. A declared prompt is the whole prompt -- it is
        assembled onto a request that has none -- so a request that already carries a system message
        is a second prompt nobody asked for, and picking one of them silently would either drop the
        agent's own instructions or ignore the ones it was given.
        """
        if self._instructions is None:
            return read_system_prompt(request.system_message)
        if request.system_message is not None:
            raise ValueError(
                "Agent Control was given this agent's instructions, and the request already carries a system "
                'message of its own. `agent_control(instructions=...)` assembles the prompt, so the agent has '
                'to have none: drop `create_agent(system_prompt=...)`, and any middleware that writes one, or '
                'drop `instructions=` and annotate the blocks of the prompt you keep with `id`s instead.'
            )
        return assemble_system_prompt(self._instructions, request)

    def _model(self, requested: str | None, config: AgentConfig) -> BaseChatModel | None:
        """The model a published `model` names, or `None` to send the request to the one it carries.

        A published `model` replaces the model the agent was *built* with, and nothing else. A
        request that arrives carrying some other model got it from a middleware ahead of this one --
        a fallback after an error, a choice made from the run's own state -- and that is a decision
        about this request, which outranks a published default exactly as a per-call
        `model_settings` does. Overwriting it would undo the one thing that middleware was added to
        do, so it is reported instead: Logfire shows a model this request is not using.
        """
        if config.model is None:
            return None
        if requested is not None and requested != self._code_model_id:
            self._require_control().report_unmatched(
                f'Managed agent config sets model {config.model!r}, but this request already carries '
                f'{requested!r} rather than the {self._code_model_id!r} the agent was built with, which means '
                'something chose it for this request; that section is not applied and the request keeps the '
                'model it arrived with.'
            )
            return None
        return build_model(config.model, self._require_control())

    def _publish(self, request: ModelRequest[Any], prompt: SystemPrompt, model_id: str | None) -> None:
        """Publish what the agent sends, from the first request that shows what that is.

        The first request rather than construction, because `create_agent` keeps the prompt, the
        model and the tool list in a closure the agent object does not expose -- so this is one
        request that was observed, not the code, and it says so: `source='observed'` is what tells
        the editor that the model and settings here are the ones *that* request carried, and the
        blocks whose text this adapter cannot attribute to the code go up as seams with no text.
        """
        control = self._require_control()
        if control.variable_name in self._published:
            return
        self._published.add(control.variable_name)
        control.publish_baseline(
            build_baseline(
                instructions=prompt.blocks,
                model=model_id,
                settings=read_settings(request.model),
                tools=read_tools(request.tools),
            ),
            source='observed',
        )


def agent_control(
    *,
    name: str | None = None,
    instructions: Mapping[str, Instruction] | None = None,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> AgentControlMiddleware:
    """Make a LangChain agent configurable from Logfire, as one middleware to add **last**.

    ```python skip-run="true" skip-reason="external-connection"
    from langchain.agents import create_agent

    import logfire
    from logfire.agent_control.langchain import agent_control

    logfire.configure()

    agent = create_agent(
        'anthropic:claude-haiku-4-5',
        tools=[get_weather],
        name='checkout_assistant',
        middleware=[
            agent_control(
                instructions={
                    'role': 'You are a concise checkout assistant.',
                    'refunds': 'Always confirm the order total before refunding.',
                },
                label='production',
            )
        ],
    )
    ```

    The prompt moves from `create_agent(system_prompt=...)` into `instructions=`, and each block
    becomes one someone can rewrite or remove in Logfire on its own. A prompt kept on `create_agent`
    still works, and is still applied to -- but only the blocks of a `SystemMessage` content list
    that name themselves with an `id` are editable, because nothing else about a request says whether
    its text came from your code or from a middleware that computed it for this one run.

    Args:
        name: The agent's name, which its config is keyed on as the Logfire variable
            `agent__<name>`. Defaults to the `name` the run says the agent has, which is what
            already identifies it in Logfire; an agent created without one has no name to key on,
            and that is an error rather than a guess. Pass it here for a key no run can move.
        instructions: The agent's prompt, block by block, instead of `create_agent`'s
            `system_prompt`. Each key is the block's id and each value is its text, or a callable
            taking the `ModelRequest` for a block this request works out for itself. Declaring the
            prompt here is what makes its blocks editable: they go into the baseline with their
            text and can be replaced or removed from Logfire one at a time, while a prompt this
            middleware merely finds on a request is a seam it cannot attribute to your code.
        label: The label to resolve, such as `'production'`. When `None`, the variable's own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do about a published entry that reaches nothing in this deployment.
            `'warn'` (the default) says so once per process, `'error'` fails the request, and
            `'ignore'` says nothing.
        publish_baseline: Whether to publish what the agent sends to Logfire, which is what the
            editor diffs published values against and what creates the variable the first time.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
            global one that `logfire.configure()` sets up.

    Returns:
        The middleware to put last in `create_agent(middleware=[...])`. It reads and applies the
        config; it never changes the agent, the model, or the tool objects you pass in.
    """
    return AgentControlMiddleware(
        name=name,
        instructions=instructions,
        label=label,
        logfire_instance=logfire_instance,
        on_unmatched=on_unmatched,
        publish_baseline=publish_baseline,
    )
