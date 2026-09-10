"""Making one Google ADK `LlmAgent` configurable from Logfire."""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.adk.tools.base_toolset import BaseToolset
from google.genai import types

from .. import (
    AgentConfig,
    AgentControl,
    Block,
    OnUnmatched,
    Resolution,
    ToolDef,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
)
from . import _instructions, _settings, _tools
from ._model import ManagedLlm, to_adk_model_name, to_canonical_model_name

if TYPE_CHECKING:
    from logfire import Logfire

__all__ = ('agent_control',)


def agent_control(
    agent: LlmAgent,
    *,
    name: str | None = None,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> LlmAgent:
    """Make an ADK agent's instructions, model, settings, and tool definitions editable from Logfire.

    The agent is wired up in place and returned -- the same object, not a copy -- so it can be
    wrapped where it is built:

    ```python skip-run="true" skip-reason="illustrative-fragment"
    agent = agent_control(
        LlmAgent(
            name='checkout_assistant',
            model='gemini-2.5-flash',
            instruction='You are a concise checkout assistant.',
        ),
        label='production',
    )
    ```

    Everything not published in Logfire keeps doing what the code says, and removing a published
    value in Logfire puts that piece back. A value Logfire cannot supply -- an unreachable Logfire, a
    missing value, one this release cannot parse -- means the same thing: the agent runs as written.

    Args:
        agent: The agent to manage, wired up in place. Its `name` is what the config is keyed on, so
            ADK's requirement that every agent have one is also this adapter's. Two things on it are
            replaced: `before_model_callback` and `after_model_callback` gain the managed hooks, and
            `model` is wrapped (see the documentation's *Known limits*).
        name: The name to key the config on, when it should differ from `agent.name`.
        label: The label to resolve, such as `'production'`. When `None`, the variable's own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do with a published value that reaches nothing in this deployment --
            an instruction id this agent does not assemble, an override naming a tool it does not
            advertise, a setting ADK or the model serving the request has no knob for. `'warn'` (the
            default) says so once per process; `'error'` fails the request; `'ignore'` says nothing.
        publish_baseline: Whether to publish the agent as this adapter observes it to Logfire, which
            is what the editor diffs published values against. Disable it when the variables token is
            intentionally read-only.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the global
            one, which is what `logfire.configure()` sets up.

    Returns:
        The same `LlmAgent`, with the managed hooks installed.
    """
    control = AgentControl(
        name or agent.name,
        label=label,
        logfire_instance=logfire_instance,
        on_unmatched=on_unmatched,
        publish_baseline=publish_baseline,
    )
    adapter = _Adapter(agent, control)
    # The managed callback goes first so the agent's own callbacks still run after it and still win:
    # a value someone passed for this one run is a deliberate, local decision, and a config published
    # for every run is not the thing that should override it.
    agent.before_model_callback = [adapter.before_model, *agent.canonical_before_model_callbacks]
    # The managed callback goes first here for the opposite reason: it puts the code's own tool names
    # back on what the model returned, so every callback after it sees the names the code gave.
    agent.after_model_callback = [adapter.after_model, *agent.canonical_after_model_callbacks]
    return agent


@dataclass(frozen=True)
class _Request:
    """What one model request resolved, carried from the hook before it to the work after it."""

    invocation_id: str
    """The ADK invocation this belongs to, so a hook never reads a neighbouring run's request."""
    resolution: Resolution
    """The one resolution this request was built from; see `ManagedLlm.current_resolution`."""
    code_names: dict[str, str]
    """Advertised name -> code-side name, for the tools a published override renamed."""


class _Adapter:
    """The per-request work of managing one agent, and the state that outlives a request.

    An instance is shared by every run of its agent, so what it holds has to be safe to share: the
    control (which is), the model wrapper (which caches only resolved models by name), a flag saying
    the baseline has been described once, and a `ContextVar` holding what the request running *in
    this task* resolved. Two concurrent runs are two tasks with two contexts, so neither can see the
    other's renames or report the other's version.
    """

    def __init__(self, agent: LlmAgent, control: AgentControl) -> None:
        self._agent = agent
        self._control = control
        self._baseline_described = False
        self._request: ContextVar[_Request | None] = ContextVar(
            f'logfire.agent_control.google_adk.{control.variable_name}', default=None
        )
        self._managed_llm: ManagedLlm | None = None
        # A model is only wrapped when the agent names one. An agent that leaves `model` empty
        # inherits its parent's, and resolving that here would pin whatever the tree happened to say
        # at wrapping time -- often before the parent exists -- so it is left to ADK and a published
        # `model` is reported as something this agent cannot switch.
        if agent.model:
            code_model = agent.canonical_model
            self._managed_llm = ManagedLlm(
                model=code_model.model, code_model=code_model, current_resolution=self._resolution
            )
            agent.model = self._managed_llm

    async def before_model(self, callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        """Describe this request to Logfire, and apply to it whatever Logfire has published.

        ADK assembles the whole request -- prompt, tools, model name, settings -- before calling this,
        and sends what it finds here afterwards, so this one hook reaches all four sections of the
        config. Returning `None` is what lets the request proceed.
        """
        agent = self._agent
        system_instruction = llm_request.config.system_instruction
        sources = await _instructions.agent_sources(agent, callback_context)
        located = _instructions.partition(system_instruction, sources) if isinstance(system_instruction, str) else []
        tools = _tools.read(llm_request, await self._toolset_labels(callback_context))

        code_names: dict[str, str] = {}
        with self._control.resolution() as resolution:
            self._describe(sources, located, tools)
            config = resolution.config
            if config is not None:
                if config.instructions is not None:
                    self._apply_instructions(llm_request, config, located, system_instruction)

                # No `reserved` names and the default global collision scope: ADK advertises every
                # tool into one namespace and dispatches from one `tools_dict` keyed by bare name,
                # and the tools it adds itself -- `transfer_to_agent` -- are advertised through the
                # same declarations as any other, so nothing is out of reach of a rename.
                applied_tools = apply_tool_definitions(tools, config, on_unmatched=self._control.on_unmatched)
                _tools.write(llm_request, applied_tools.tools)
                forward, code_names = _tools.renames(applied_tools.routes)
                _tools.advertise(llm_request, forward)

                if config.model is not None:
                    self._apply_model(llm_request, config.model)

                backend = _settings.backend_of(self._serving_model(llm_request))
                patch = apply_settings(
                    config, supported=_settings.CONFIGURABLE, on_unmatched=self._control.on_unmatched
                )
                for message in _settings.apply(llm_request.config, patch, backend):
                    self._control.report_unmatched(message)

        # Kept for what happens after this hook returns and the resolution's own block is left: the
        # model call this request turns into, and the response ADK dispatches from.
        self._request.set(
            _Request(invocation_id=callback_context.invocation_id, resolution=resolution, code_names=code_names)
        )

    def after_model(self, callback_context: CallbackContext, llm_response: LlmResponse) -> None:
        """Translate a renamed call back into the name the code gave it, before ADK dispatches it.

        Returning `None` is what leaves the response ADK's own; the translation is a replacement of
        the parts that name a tool, which is what the rest of the invocation goes on to read.
        """
        request = self._request.get()
        if request is None or request.invocation_id != callback_context.invocation_id:
            # A response from an invocation this task did not build a request for. Nothing about it
            # is this request's to rewrite, and guessing at a mapping would rename someone else's
            # call.
            return
        _tools.to_code_names(llm_response, request.code_names)

    def _apply_instructions(
        self, llm_request: LlmRequest, config: AgentConfig, located: list[Block], system_instruction: Any
    ) -> None:
        """Swap published text into the prompt, or say why this request has no prompt to swap it into."""
        if not isinstance(system_instruction, str):
            self._control.report_unmatched(
                'Managed agent config publishes instructions, but this request carries a system '
                'instruction that is not text; those instructions are not applied.'
            )
            return
        applied = apply_instructions(located, config, on_unmatched=self._control.on_unmatched).blocks
        joined = _instructions.join(applied)
        # Only written when it differs, so a config that publishes instructions this request has
        # nothing to apply leaves the prompt as the exact object ADK assembled rather than as this
        # adapter's re-join of its own partition of it.
        if joined != system_instruction:
            llm_request.config.system_instruction = joined

    def _resolution(self) -> Resolution | None:
        """What the request running in this task resolved, for the work that happens after the hook."""
        request = self._request.get()
        return request.resolution if request is not None else None

    def _describe(self, sources: list[Block], located: list[Block], tools: list[ToolDef]) -> None:
        """Publish what this adapter can see of the agent, once, from the first request it assembles.

        The first request rather than construction time, because that is the first moment ADK has
        answered the questions the baseline asks: which toolsets resolved to which tools, what the
        planner and the tools contributed to the prompt, and what the identity line says. That also
        makes it an observation rather than a reading of the code -- an agent whose tool list varies
        with its input publishes the list the first request carried -- so it is published as one.
        """
        if self._baseline_described:
            return
        self._baseline_described = True
        code_model = self._managed_llm.code_model if self._managed_llm is not None else None
        self._control.publish_baseline(
            build_baseline(
                instructions=_instructions.baseline_blocks(sources, located),
                model=to_canonical_model_name(code_model.model) if code_model and code_model.model else None,
                settings=_settings.describe(self._code_config(), _settings.backend_of(self._code_model())),
                tools=tools,
            ),
            source='observed',
        )

    def _code_config(self) -> types.GenerateContentConfig | None:
        """The settings the agent as written actually sends, which is not only its own config object.

        A `BuiltInPlanner` overwrites `thinking_config` on every request it touches, so the thinking
        the agent does is the planner's rather than the one its `generate_content_config` names. The
        baseline says what the agent does, so it says the planner's -- built here the same way ADK
        builds it, on a copy, since the agent's own object is shared with every run.
        """
        config = self._agent.generate_content_config
        planner = self._agent.planner
        if isinstance(planner, BuiltInPlanner):
            base = config if config is not None else types.GenerateContentConfig()
            return base.model_copy(update={'thinking_config': planner.thinking_config})
        return config

    def _code_model(self) -> BaseLlm:
        """The model the agent was written with, wrapper or no wrapper."""
        managed = self._managed_llm
        return managed.code_model if managed is not None else self._agent.canonical_model

    def _serving_model(self, llm_request: LlmRequest) -> BaseLlm:
        """The model this request will actually be sent to, published switch included."""
        managed = self._managed_llm
        return managed.serving(llm_request.model) if managed is not None else self._agent.canonical_model

    def _apply_model(self, llm_request: LlmRequest, model: str) -> None:
        """Point this request at the published model, if ADK can route the name at all.

        Two names are tried: the canonical `provider:model` translated into ADK's convention, and the
        published string exactly as it was written. The second is what lets an ADK-native name --
        `gemini-2.5-flash`, or a `Class:model` override -- be published directly, and what rescues a
        provider whose ADK spelling this adapter's table gets wrong.
        """
        managed = self._managed_llm
        if managed is None:
            self._control.report_unmatched(
                f'Managed agent config selects model {model!r}, but this agent inherits its model from its '
                'parent rather than naming one; that model is not applied.'
            )
            return
        for name in dict.fromkeys((to_adk_model_name(model), model)):
            resolved = managed.resolve(name)
            if resolved is not None:
                llm_request.model = name
                self._report_capability_change(model, resolved)
                return
        self._control.report_unmatched(
            f'Managed agent config selects model {model!r}, which Google ADK cannot resolve to a model '
            'class -- it may need a provider extra this deployment has not installed; the agent keeps the '
            'model it was written with.'
        )

    def _report_capability_change(self, model: str, serving: BaseLlm) -> None:
        """Say so when the model that will serve a request is not the one it was assembled for.

        ADK asks the *agent's* model what it supports while it builds the request -- whether an
        output schema can be sent alongside tools, today -- and that happens before any hook can say
        that a published model will serve it instead. The switch still applies; what cannot follow it
        is the shape of the request, so a deployment that would rather not send one model's request
        to another model's API is the one who gets to decide.
        """
        code_model = self._code_model()
        if serving is not code_model and serving.capabilities != code_model.capabilities:
            self._control.report_unmatched(
                f'Managed agent config selects model {model!r}, which reports different capabilities than '
                f'{code_model.model!r}, the model Google ADK had already assembled this request for; the model '
                'is switched but the request keeps the shape the code model gave it.'
            )

    async def _toolset_labels(self, callback_context: CallbackContext) -> dict[str, str]:
        """Which toolset each of this request's tools came from, for the editor to group them by.

        ADK flattens toolsets into one list of tools before the request is assembled, so the grouping
        is recovered by asking each toolset what it contributed. That answer is cached per invocation
        by ADK itself, so on the common path this costs a dictionary lookup rather than a second trip
        to an MCP server.

        A toolset with no `tool_name_prefix` is labelled by its class, but only when this agent has
        exactly one toolset of that class. An override narrowed to a group only means anything if the
        label the editor was shown addresses one group, and two `MCPToolset`s side by side would
        otherwise be shown -- and patched -- as if they were one. The second of them is better left
        ungrouped than grouped wrongly.
        """
        # ADK's own `ToolUnion` includes a bare callable it does not describe the parameters of.
        entries: list[Any] = self._agent.tools  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        toolsets = [entry for entry in entries if isinstance(entry, BaseToolset)]
        shared = Counter(type(toolset).__name__ for toolset in toolsets if not toolset.tool_name_prefix)
        labels: dict[str, str] = {}
        for toolset in toolsets:
            label = toolset.tool_name_prefix or type(toolset).__name__
            if not toolset.tool_name_prefix and shared[label] > 1:
                continue
            try:
                tools = await toolset.get_tools_with_prefix(callback_context)
            except Exception:
                # A toolset that cannot list itself right now is a grouping label this request does
                # not get. It is not a reason to fail a request the agent is otherwise ready to make,
                # and ADK has already listed the tools that reached the model.
                continue
            for tool in tools:
                labels[tool.name] = label
        return labels
