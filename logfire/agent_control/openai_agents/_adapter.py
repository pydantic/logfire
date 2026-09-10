"""Agent Control for the OpenAI Agents SDK: one `Model` wrapper, installed on the agent."""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Any, TypeVar

from agents import Agent, ModelSettings, RunContextWrapper, Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.models.default_models import get_default_model
from agents.models.interface import Model, ModelProvider, ModelTracing
from agents.models.multi_provider import MultiProvider
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel

from .. import (
    AgentConfig,
    AgentControl,
    Block,
    OnUnmatched,
    ToolDef,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
    merge_settings,
    use_resolution,
)
from .._reporting import warn_dropped
from ._instructions import (
    AGENT_BLOCK_ID,
    InstructionSource,
    Sources,
    baseline_blocks,
    instructions_renderer,
    order_sources,
)
from ._models import to_canonical_model_name, to_sdk_model_name
from ._run import Run, begin_run, current_run, resolve
from ._settings import SETTING_FIELDS, baseline_settings, lower_settings, settings_layer, supported_settings
from ._tools import (
    advertise,
    advertised_names,
    rename_history,
    rename_response,
    rename_stream_event,
    rename_tool_choice,
    reserved_names,
    tool_definitions,
)

if TYPE_CHECKING:
    from agents.retry import ModelRetryAdvice, ModelRetryAdviceRequest
    from openai.types.responses.response_prompt_param import ResponsePromptParam

    from logfire import Logfire

TContext = TypeVar('TContext')
TDerived = TypeVar('TDerived')

MANAGED_FIELDS = frozenset(SETTING_FIELDS.values())
"""The `ModelSettings` fields a published config can reach, and the only ones merged by provenance."""

RUN_AWARE_SETTINGS = '_agent_control_run_aware'
"""Marks a `ModelSettings` whose `resolve` records the keys a per-run override named; see below.

An attribute rather than an `isinstance` check because the class is derived per object, from whatever
class the caller's own settings had. What matters is only whether this object already has the seam.
"""


def agent_control(
    agent: Agent[TContext],
    *,
    name: str | None = None,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
    instructions: Mapping[str, InstructionSource] | None = None,
    provider: ModelProvider | None = None,
) -> Agent[TContext]:
    """Make an agent's instructions, model, model settings, and tool descriptions editable from Logfire.

    Returns a copy of `agent` that runs exactly as written until something is published for it in
    Logfire, and applies whatever *is* published from then on. Run it the way you run any other agent:

    ```python skip-run="true" skip-reason="illustrative-fragment"
    from agents import Agent, Runner
    from logfire.agent_control.openai_agents import agent_control

    agent = agent_control(
        Agent(name='checkout_assistant', instructions='You are a concise checkout assistant.'),
        label='production',
    )
    result = await Runner.run(agent, 'Refund my last order.')
    ```

    Args:
        agent: The agent to manage. It is copied, never modified, so the agent you passed keeps
            running on its code and can be wrapped again for another label. Each agent in a handoff
            chain is its own configuration and has to be wrapped in its own right.
        name: The name the config is keyed on, as `agent__<name>`. Defaults to `agent.name`, which
            the SDK already requires and already uses to name this agent in traces, so the config
            and the spans you are reading it against agree by construction.
        label: The label to resolve, such as `'production'`. When `None`, the variable's own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do about a published entry that reaches nothing here -- an instruction
            id this agent does not assemble, an override for a tool it does not have, a setting this
            SDK cannot send, a model this process cannot build. `'warn'` (the default) says so once
            per process, `'error'` fails the request, and `'ignore'` says nothing.
        publish_baseline: Whether to publish the code baseline the Logfire editor diffs against, on
            the first model request. Disable it when the variables token is intentionally read-only.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
            global one, which is what `logfire.configure()` sets up.
        instructions: The prompt as named blocks, so a published value can address one of them
            instead of replacing the whole prompt. Each is either fixed text or the SDK's own
            `(run_context, agent)` callable. The mapping *is* the agent's prompt: pass an agent
            without its own `instructions`, and give one block the id `'agent'` if you want the
            reserved name for the main one. Fixed blocks are sent first, in declaration order, so a
            per-request block never moves the cacheable prefix.
        provider: The `ModelProvider` that resolves model names, defaulting to `MultiProvider()` --
            the same default the SDK itself has. Pass yours here if you have one: this wrapper
            resolves the model itself, so a `RunConfig(model_provider=...)` is no longer consulted
            for this agent.

    Returns:
        A copy of `agent`, with the managed prompt, model and settings installed. It is an `Agent`
        in every respect, of a one-off subclass of the class you passed: the SDK's per-turn
        `get_all_tools` is where this adapter resolves the config once for a whole run, which is what
        lets the prompt and the model request of one turn apply the same published version.

    Raises:
        ValueError: If the agent has no name to key its config on, or if `instructions` blocks are
            given for an agent that also carries its own `instructions`.
    """
    control_name = agent.name if name is None else name
    if not control_name.strip():
        raise ValueError(
            'Agent Control needs a name for this agent: its config is stored under `agent__<name>`, and '
            'that name is how the Logfire UI matches the config to the agent you already see in traces. '
            'Give the agent a name -- `Agent(name=...)` -- or pass one as `agent_control(agent, name=...)`.'
        )
    if instructions is None:
        # An agent that declares no blocks has exactly one, under the id the contract reserves.
        sources: Sources = () if agent.instructions is None else ((AGENT_BLOCK_ID, agent.instructions),)
    elif agent.instructions is not None:
        raise ValueError(
            f'Agent {control_name!r} was given `instructions` blocks as well as its own `Agent(instructions=...)`, '
            "and only one of them can be the prompt. The blocks are the whole prompt, so move the agent's own "
            "text in as a block -- conventionally `{'agent': ...}` -- and leave `Agent(instructions=...)` unset."
        )
    elif not instructions:
        raise ValueError(f'Agent {control_name!r} was given an empty mapping of `instructions` blocks.')
    else:
        sources = order_sources(instructions)

    control = AgentControl(
        control_name,
        label=label,
        logfire_instance=logfire_instance,
        on_unmatched=on_unmatched,
        publish_baseline=publish_baseline,
    )
    model = _ControlledModel(
        control,
        code_model=agent.model,
        code_settings=agent.model_settings,
        code_instructions=baseline_blocks(sources),
        provider=MultiProvider() if provider is None else provider,
        publish_baseline=publish_baseline,
    )
    changes: dict[str, Any] = {
        'model': model,
        # Always installed, even for an agent whose prompt is one string and even for one with no
        # prompt at all: the section composes rather than replaces, so a published block has to be
        # able to add itself to a prompt that has nothing in it.
        'instructions': instructions_renderer(control, sources),
        'model_settings': agent.model_settings,
    }
    managed = agent.clone(**changes)
    # Put the settings back afterwards as well, because `Agent.__post_init__` resets any that match
    # the SDK's global defaults to the ones the agent's *model* implies -- and this agent's model is
    # now an object, whose implied settings are empty. Without this, wrapping an agent that never
    # touched `model_settings` would silently drop the reasoning effort and verbosity its model name
    # picked, which is a change in what the agent does before anything is even published.
    managed.model_settings = _run_aware_settings(control, agent.model_settings)
    _install_run_seam(managed)
    return managed


def _derive(instance: TDerived, namespace: dict[str, Any]) -> TDerived:
    """`instance`, rebound to a one-off subclass of its own class carrying `namespace`.

    The two SDK seams this adapter needs -- the per-turn `Agent.get_all_tools`, and the settings merge
    in `ModelSettings.resolve` -- are methods, so reaching them means overriding them, and the class
    to override is whichever one the caller's object already has: an `Agent` subclass of their own, or
    a `ModelSettings` subclass the SDK is happy to carry through `clone`. Deriving from
    `type(instance)` keeps everything they added, and rebinding the object rather than rebuilding it
    keeps every field exactly as the SDK constructed it, `__post_init__` coercions included.
    """
    base = type(instance)
    derived = type(f'AgentControl{base.__name__}', (base,), {'__doc__': base.__doc__, **namespace})
    # Set through `object` because `__class__` is not statically assignable on a type variable, which
    # is the whole point of doing it: what comes back is the object that went in, typed as it was.
    object.__setattr__(instance, '__class__', derived)
    return instance


def _install_run_seam(agent: Agent[TContext]) -> None:
    """Make `agent` resolve its config once per run, at the one hook that both applications can read.

    `get_all_tools` is awaited directly by the runner at the top of every turn, in the coroutine that
    goes on to render the prompt and then call the model, and it is handed the run's context, which is
    the run's identity. Nothing else the SDK offers is both: the prompt is rendered in a task of the
    runner's own, and the model is handed the finished prompt and nothing about the run. So this is
    where the run's `Resolution` is established, and both hooks read that one value back out of it.
    """
    base = type(agent)

    async def get_all_tools(self: Agent[TContext], run_context: RunContextWrapper[TContext]) -> list[Tool]:
        model = self.model
        if isinstance(model, _ControlledModel):
            model.begin_run(run_context)
            if not getattr(self.model_settings, RUN_AWARE_SETTINGS, False):
                # `clone(model_settings=...)` hands back a plain `ModelSettings`, and with it the
                # SDK's own merge, which keeps no record of which keys a `RunConfig(model_settings=)`
                # named -- so a run repeating a value the code already had would look like a run that
                # asked for nothing, and lose the key to the published config. This hook is the one
                # seam a clone keeps, so the settings seam is put back through it, once.
                self.model_settings = model.run_aware_settings(self.model_settings)
        return await base.get_all_tools(self, run_context)

    _derive(agent, {'get_all_tools': get_all_tools})


def _run_aware_settings(control: AgentControl, settings: ModelSettings) -> ModelSettings:
    """`settings`, recording which of its fields a per-run override sets, for the run in progress.

    `ModelSettings.resolve` is where the SDK folds a `RunConfig(model_settings=...)` into the agent's
    own, and it is the last moment the two are distinguishable: what a model is handed is one merged
    object with no record of who set what. Capturing the override's keys here is what makes the
    contract's precedence exact rather than a guess -- a run that passes the value the code already
    had is invisible in the merged object, and reading that as "the run did not set this" would let a
    published value win a key the caller overrode.
    """
    base = type(settings)

    def resolve_settings(self: ModelSettings, override: ModelSettings | dict[str, Any] | None) -> ModelSettings:
        run = current_run(control.variable_name)
        if run is not None:
            run.explicit_settings = _explicit_fields(override)
        return base.resolve(self, override)

    return _derive(copy.copy(settings), {'resolve': resolve_settings, RUN_AWARE_SETTINGS: True})


def _explicit_fields(override: ModelSettings | dict[str, Any] | None) -> frozenset[str]:
    """The managed `ModelSettings` fields a per-run override actually sets.

    The same reading the SDK's own merge takes: a field is set when the override carries a value for
    it that is not `None`, whether the override arrived as a `ModelSettings` or as the dict form the
    SDK also accepts. Narrowed to the fields a published config can reach, since no other field has
    two layers for this adapter to arbitrate between.
    """
    if override is None:
        return frozenset[str]()
    if isinstance(override, dict):
        values: Mapping[str, Any] = override
    else:
        values = {field.name: getattr(override, field.name) for field in fields(override)}
    return frozenset(name for name, value in values.items() if value is not None) & MANAGED_FIELDS


def _baseline_model_name(model: str | Model | None) -> str | None:
    """The canonical `provider:model` string a baseline describes the agent's own model with.

    An agent that names no model runs on the SDK's default, so that is what the baseline says: it is
    the model the editor's reader is looking at in their traces. An agent given a `Model` *object* is
    read for the name it was built with when it is one of the SDK's own OpenAI models, which carry it
    as a plain string; anything else -- a model class of someone's own, a name that is not a string --
    is left out rather than guessed at, since a baseline naming the wrong model would offer an
    override that the code then ignored.
    """
    if not isinstance(model, Model):
        return to_canonical_model_name(model or get_default_model())
    if isinstance(model, (OpenAIResponsesModel, OpenAIChatCompletionsModel)):
        name = getattr(model, 'model', None)
        if isinstance(name, str):
            return f'openai:{name}'
    return None


@dataclass(frozen=True)
class _Request:
    """One model request, with everything a published config had to say about it already applied."""

    model: Model
    system_instructions: str | None
    input: str | list[TResponseInputItem]
    model_settings: ModelSettings
    tools: list[Tool]
    routes: Mapping[str, str]
    """Advertised tool name -> code-side name, for renaming a call back on the way out."""


class _ControlledModel(Model):
    """The agent's model, with a published config applied to every request that passes through it.

    Three of the four managed sections are applied here, because this is the one place in the SDK
    that sees them all: the tool list and the settings arrive as arguments, and which model runs is
    decided here rather than by the runner, since a wrapper *is* the agent's model and resolves what
    it delegates to. (Instructions are applied where they are assembled, one call earlier.)

    Both hooks apply the *run's* resolution, established once at the seam this adapter installs on the
    agent; see `_run`. It is entered again around each call, so the provider's own generation span --
    the one Logfire records the request from -- carries the label and version that produced it.
    """

    def __init__(
        self,
        control: AgentControl,
        *,
        code_model: str | Model | None,
        code_settings: ModelSettings,
        code_instructions: Sequence[Block],
        provider: ModelProvider,
        publish_baseline: bool,
    ) -> None:
        self._control = control
        self._code_model = code_model
        self._code_settings = code_settings
        self._code_instructions = code_instructions
        self._provider = provider
        self._publish = publish_baseline
        """Whether to describe the agent at all, which the core is told separately.

        Kept here as well because the core's flag decides whether a baseline is *written*, and this
        one decides whether it is built -- which is work on the first request's own thread, including
        resolving the agent's own model. A deployment that turned publishing off is asking for
        neither.
        """
        self._published = False
        self._resolved: dict[str | None, Model] = {}
        """Every model this wrapper has asked a provider for, under the name it asked for.

        A cache rather than a log: resolving one name twice builds a second object holding a second
        client, and nothing would ever close the first. Keyed by name, so it only ever grows and two
        concurrent runs cannot disagree about it -- *which* model a run used is that run's own
        business, and lives on that run's record.
        """

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self._control!r}, code_model={self._code_model!r})'

    def begin_run(self, run_context: RunContextWrapper[Any]) -> Run:
        """Resolve this agent's config for the run `run_context` identifies, once; see `_run`."""
        return begin_run(self._control, run_context)

    def run_aware_settings(self, settings: ModelSettings) -> ModelSettings:
        """`settings`, recording which of its fields a per-run override sets for this agent's runs."""
        return _run_aware_settings(self._control, settings)

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        run = current_run(self._control.variable_name)
        resolution = run.resolution if run is not None else resolve(self._control)
        with use_resolution(resolution):
            request = self._prepare(run, resolution.config, system_instructions, input, model_settings, tools, handoffs)
            response = await request.model.get_response(
                request.system_instructions,
                request.input,
                request.model_settings,
                request.tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )
            return rename_response(response, request.routes)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        run = current_run(self._control.variable_name)
        resolution = run.resolution if run is not None else resolve(self._control)
        with use_resolution(resolution):
            request = self._prepare(run, resolution.config, system_instructions, input, model_settings, tools, handoffs)
            stream = request.model.stream_response(
                request.system_instructions,
                request.input,
                request.model_settings,
                request.tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )
            async for event in stream:
                yield rename_stream_event(event, request.routes)

    def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
        """Whatever the model *this run's* last request went to would advise; retries are the runner's.

        Asked of the wrapper right after a request through it failed, and answered by the model that
        request actually went to. A wrapper is shared by every concurrent run of its agent, so the
        model of whichever request went last is the wrong one to ask: two runs on two published models
        would trade each other's replay-safety and retry-after advice.
        """
        run = current_run(self._control.variable_name)
        if run is None or not run.models:
            return None
        return run.models[-1].get_retry_advice(request)

    async def close(self) -> None:
        """Release every model this wrapper resolved, and the one the agent was written with."""
        for model in self._owned():
            await model.close()

    async def _cleanup_on_run_end(self, owner: object) -> None:
        """Tell the models *this run* used that it ended, which only this wrapper is told.

        Forwarded because the runner calls it on the model it was given -- this wrapper -- and a model
        that holds a connection per run (the websocket-backed Responses model) would otherwise never
        be told the run ended. Forwarded to the run's own models, and to every one of them, since a
        run whose config changed models mid-flight holds a connection on each.
        """
        run = current_run(self._control.variable_name)
        for model in run.models if run is not None else ():
            await model._cleanup_on_run_end(owner)

    def _owned(self) -> list[Model]:
        """Every distinct model instance this wrapper is responsible for shutting down."""
        owned = list(self._resolved.values())
        if isinstance(self._code_model, Model) and not any(model is self._code_model for model in owned):
            owned.append(self._code_model)
        return owned

    def _provided_model(self, name: str | None) -> Model:
        """The model the agent's own provider gives for `name`, resolved once and kept."""
        model = self._resolved.get(name)
        if model is None:
            model = self._resolved[name] = self._provider.get_model(name)
        return model

    def _code_model_instance(self) -> Model:
        """The model this agent runs on with nothing published, which is what the baseline describes."""
        if isinstance(self._code_model, Model):
            return self._code_model
        return self._provided_model(self._code_model)

    def _managed_model(self, config: AgentConfig | None) -> Model | None:
        """The published model, or `None` when none is published or the published one cannot be built.

        The contract's `provider:model` is not a name any SDK provider knows, and translating it is
        the whole of what this adapter does with the section: what comes out the other side is
        whatever the user's own `ModelProvider` -- the default `MultiProvider`, or one wired to their
        gateway -- makes of the translated name.

        Which is a call that can fail for reasons that have nothing to do with the agent: a gateway
        extra that is not installed, a provider id nobody registered. Failing the request over it
        would make a published value able to take the agent down, so a failure is reported under
        `on_unmatched` like any other section that reached nothing, and the agent keeps its own model.
        """
        if config is None or config.model is None:
            return None
        try:
            return self._provided_model(to_sdk_model_name(config.model))
        except Exception as exc:
            self._control.report_unmatched(
                f'Managed agent config selects model {config.model!r}, which this process could not resolve '
                f'({exc}); that section is not applied and the agent keeps the model it has in code.'
            )
            return None

    def _publish_baseline(self, tools: Sequence[ToolDef], code_model: Callable[[], Model]) -> None:
        """Describe the agent as written, once, from the first request that can see all of it.

        The first request rather than construction, because that is the first moment the agent's
        tools are knowable: `Agent.get_all_tools` is what the runner hands a model, and it is where a
        tool gated on `is_enabled` is admitted and a tool an MCP server contributed arrives. The core
        is what makes the publish itself happen once per process; the two flags here keep a baseline
        from being *built*, and the code model from being resolved -- on every request after the
        first, and at all for a deployment that turned publishing off.

        Everything in it is read off the agent -- its declared blocks, its own settings, the
        definitions of the tools it declares -- so it is published as the code baseline it is. A block
        computed per request contributes its seam and no text, which is what keeps one run's rendering
        of it out of a variable every member of the project can read.

        What it says about the settings is what a request would actually be able to apply, asked of
        the model the *code* runs on -- so `code_model` is resolved here, once, even on a request a
        published model is serving. A penalty the Responses API has no request field for is not a knob
        to show the editor, and a baseline whose settings and whose overrides disagreed about which
        ones exist would be the discrepancy this section is meant to remove.
        """
        if self._published or not self._publish:
            return
        self._published = True
        try:
            supported = supported_settings(code_model())
        except Exception as exc:
            # Which settings the editor can be offered depends on which model class the code runs on,
            # and a provider that cannot build the agent's own model cannot answer that. Publishing
            # nothing is then the honest outcome -- and only the baseline is lost, because a request
            # this far in is being served by a published model that *did* resolve. Never raised: a
            # baseline is Agent Control describing the code, and describing it is not worth failing a
            # request over. Not reported under `on_unmatched` either, since nothing was published
            # that this could be said to have not applied.
            warn_dropped(
                f'Agent Control could not describe agent {self._control.name!r} to Logfire: its own model '
                f'{self._code_model!r} is one this process cannot resolve ({exc}). The agent runs, and the '
                'Logfire editor has no code baseline to diff published values against until it can.'
            )
            return
        self._control.publish_baseline(
            build_baseline(
                instructions=self._code_instructions,
                model=_baseline_model_name(self._code_model),
                settings=baseline_settings(self._code_settings, supported),
                tools=tools,
            ),
            source='code',
        )

    def _prepare(
        self,
        run: Run | None,
        config: AgentConfig | None,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: Sequence[Handoff],
    ) -> _Request:
        """Apply one resolved config to one request, for every section but the instructions.

        Instructions are applied where they are assembled, in the `Agent.instructions` callable the
        adapter installs, so what arrives here is already the managed prompt.
        """
        definitions = tool_definitions(tools)
        self._publish_baseline(definitions, self._code_model_instance)
        model = self._managed_model(config) or self._code_model_instance()
        if run is not None:
            run.used(model)
        if config is None:
            # Nothing published, unreachable, or unparseable: the agent runs exactly as written, and
            # every argument reaches the model untouched.
            return _Request(model, system_instructions, input, model_settings, tools, {})

        on_unmatched = self._control.on_unmatched
        applied = apply_tool_definitions(
            definitions, config, on_unmatched=on_unmatched, reserved=reserved_names(tools, handoffs)
        )
        advertised = advertised_names(applied)
        published = lower_settings(
            apply_settings(config, supported=supported_settings(model), on_unmatched=on_unmatched), model_settings
        )
        # Code first, published over it, and the keys this run set explicitly over both, which is the
        # contract's precedence. The run's keys are the ones captured where the SDK merged them in
        # rather than the ones that happen to differ from the code: a run passing the value the code
        # already had is asking for that value, not inheriting it.
        #
        # Both layers are read off the settings *this request* carries, which is the agent's own with
        # the run's override merged in -- so a key the run did not name still holds the agent's value,
        # and the two layers are exactly the request split by who set what. Reading the code layer off
        # the settings captured at wrapping time would say the same thing for the agent that was
        # wrapped and the wrong thing for a `clone(model_settings=...)` of it, whose settings would be
        # silently replaced by the ones its original was written with.
        explicit = run.explicit_settings if run is not None else frozenset[str]()
        merged = merge_settings(
            settings_layer(model_settings, only=MANAGED_FIELDS - explicit),
            published,
            settings_layer(model_settings, only=explicit),
        )
        return _Request(
            model=model,
            system_instructions=system_instructions,
            input=rename_history(input, advertised),
            model_settings=replace(
                model_settings,
                **merged.settings,
                # The one other place a tool's name reaches the model, and a code-defined decision
                # that has to survive an overlay that only meant to rename the tool.
                tool_choice=rename_tool_choice(model_settings.tool_choice, advertised),
            ),
            tools=advertise(tools, applied),
            routes=applied.routes,
        )
