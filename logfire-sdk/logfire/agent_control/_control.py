"""Back an agent's Agent Control configuration with one Logfire variable."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import logfire
from logfire.variables import ResolutionReason, ResolvedVariable, Variable

from ._config import AgentConfig
from ._hint import DEFAULT_FRAMEWORK, BaselinePublication, BaselineSource, emit_config_hint
from ._names import agent_variable_name
from ._reporting import ApplyIssue, OnUnmatched, report_issues, report_unmatched, warn_dropped

if TYPE_CHECKING:
    from logfire import Logfire


@dataclass(frozen=True)
class Resolution:
    """One reading of an agent's managed config, and which published version it came from.

    The config is what to apply; the rest is what to say about it. A run that reports the label and
    version it resolved is what lets the Logfire UI tell a wired-up agent from one that merely has a
    config, and lets a regression be traced back to the version that produced it.
    """

    config: AgentConfig | None
    """The published config, or `None` to run the agent exactly as written; see `AgentControl.resolve`."""
    label: str | None
    """The label the value came from, or `None` when nothing was published for this agent."""
    version: int | None
    """The version of that label's value, or `None` when nothing was published."""
    reason: ResolutionReason
    """Why the variable resolved this way.

    `'resolved'` and `'context_override'` are the two that carry a config. The rest are the ways
    Logfire can have nothing to say -- `'code_default'`, `'missing_config'`, `'no_provider'`,
    `'unrecognized_variable'`, `'validation_error'`, `'other_error'` -- kept apart here because an
    adapter reporting *why* an agent is running on its code is more useful than one reporting that it
    is. `'other_error'` also covers a resolution that raised outright.
    """
    variable_name: str
    """The Logfire variable this was read from, which is also the key its telemetry is reported under."""

    _reportable: bool = field(default=True, repr=False, compare=False)
    """Whether there is a resolution to report at all.

    False only when reading the variable raised outright, which is the one case with no telemetry
    context to establish or re-establish. It is not read off `reason`, which would conflate that with
    a provider error the SDK *did* resolve through -- one that `AgentControl.resolution` reports as
    the code default, and that `reported` therefore has to report the same way.
    """

    def reported(self) -> AbstractContextManager[None]:
        """Put this resolution's label and version back on the spans of a later block.

        [`AgentControl.resolution`][logfire.agent_control.AgentControl.resolution] already does this
        for the block it wraps, which is all an adapter needs when one hook spans the run. An adapter
        whose framework resolves in one place and runs the model in another -- a graph node that
        cannot hold a context open across the nodes after it -- reads the resolution once, carries it
        in the framework's own state, and wraps each later block in this, so every span of the run
        still says which published version produced it.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        with resolution.reported():
            ...  # spans emitted here carry the resolved label and version
        ```

        Re-entrant and safe to use concurrently: each block establishes its own context rather than
        sharing one. It does nothing when there was no resolution to report, so an adapter does not
        have to branch on that.
        """
        return self._reported()

    @contextmanager
    def _reported(self) -> Generator[None]:
        if not self._reportable:
            yield
            return
        # Rebuilt rather than held: what the telemetry context *is* is the name, label and version,
        # and one `ResolvedVariable` carries a single exit stack that concurrent blocks would unwind
        # from under each other.
        with ResolvedVariable[AgentConfig | None](
            name=self.variable_name,
            value=self.config,
            label=self.label,
            version=self.version,
            reason=self.reason,
        ):
            yield


class AgentControl:
    """Manage one agent's config through its `agent__<name>` Logfire variable.

    The variable holds an [`AgentConfig`][logfire.agent_control.AgentConfig]. Each present section --
    `instructions`, `model`, `settings`, or `tool_definitions` -- is managed from Logfire, while an
    absent section keeps the code-defined behavior. Removing a section in Logfire deliberately reverts
    that section to code. There is no third state.

    This class owns the transport, and nothing else: it names the variable, reads the published value,
    and reports the code baseline the Logfire editor diffs against. What a published value *does* to
    a request lives in the pure helpers -- [`apply_instructions`][logfire.agent_control.apply_instructions],
    [`apply_tool_definitions`][logfire.agent_control.apply_tool_definitions], and
    [`apply_settings`][logfire.agent_control.apply_settings] -- so an adapter for any agent framework
    is this object plus the framework's own per-request hook:

    ```python
    from logfire.agent_control import AgentControl, Block, apply_instructions, build_baseline

    control = AgentControl('checkout_assistant', label='production')
    blocks = [Block('You are a checkout assistant.', id='agent')]

    with control.resolution() as resolution:
        control.report_baseline(build_baseline(instructions=blocks), resolution)
        if resolution.config is not None:
            applied = apply_instructions(blocks, resolution.config)
            blocks = applied.blocks
            control.report(*applied.issues)
    ```

    Nothing published can crash the *SDK*. An unreachable provider, a missing value, or one this
    version of the contract cannot parse leaves `resolve()` returning `None`, which means "run the
    agent as written"; beyond that, a value the contract can't act on costs only the piece containing
    it -- one setting, one tool, one block -- and is reported under `on_unmatched`.

    It is not a promise about the request. A setting the adapter *can* lower is forwarded to the
    provider, and providers refuse settings: a published `presence_penalty` is a `400` on some
    models, as is a `temperature` alongside a reasoning effort. Which settings a given model accepts
    is not in this contract and is not something the Logfire editor can warn about -- it is the
    adapter's own reasoning, and [`AgentSupport`][logfire.agent_control.AgentSupport] declares only
    what the *adapter* can apply.
    """

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        logfire_instance: Logfire | None = None,
        on_unmatched: OnUnmatched = 'warn',
        framework: str = DEFAULT_FRAMEWORK,
        report_baseline: BaselinePublication | None = None,
    ) -> None:
        """Declare the variable backing one agent's managed config.

        Args:
            name: The agent's name. Kept as given for display, and normalized to the key the
                variable is stored under -- lowercased, with everything outside `[a-z0-9_]` turned
                into `_` -- by
                [`agent_variable_name`][logfire.agent_control.agent_variable_name], which is the rule
                the Logfire UI and every other SDK apply too, so `checkout-assistant` here and
                `Checkout Assistant` in another service reach the same config. Explicit rather than
                derived from a framework's agent object, because the config *is* keyed on it: a name
                inferred from a class or a Python variable would silently point the agent at a
                different managed config the day someone renames it.
            label: The label to resolve, such as `'production'`. When `None`, the variable's own
                targeting rules and rollout choose which label this process gets.
            logfire_instance: The Logfire instance to resolve through, and to report the baseline on.
                Defaults to the global one, which is what `logfire.configure()` sets up.
            on_unmatched: The policy for published entries that reach nothing. Applied by
                [`report`][logfire.agent_control.AgentControl.report], which is the one place it is
                applied: the pure helpers plan a request and hand back what they could not apply, so
                an adapter reports every section's issues together and `'error'` names all of them.
                See [`OnUnmatched`][logfire.agent_control.OnUnmatched].
            framework: Which Agent Control SDK produced this agent's hints, as
                `agent_control.framework` reports it. An adapter names its framework --
                `'pydantic-ai'`, `'mastra'`, `'openai-agents'` -- because the ids a baseline addresses
                its instruction blocks by are each implementation's own, so a consumer has to know
                whose baseline it is reading. An application driving this core directly has no
                framework to name and can leave it alone; see `DEFAULT_FRAMEWORK`.
            report_baseline: How much of the code baseline leaves this process on the hint span; see
                [`BaselinePublication`][logfire.agent_control.BaselinePublication]. Defaults to
                `'structure'` when the baseline was `'observed'` and `'text'` when it was read off the
                code, which is where the two differ: code-side text is the author's, written knowing
                it is editable from this Logfire project, while text snapshotted from a request is
                whoever's request it happened to be. Set it explicitly to hold a code-side baseline to
                its seams as well, which is what a deployment whose prompts are not for every member
                of its Logfire project wants.
        """
        variable_name = agent_variable_name(name)

        self.name = name.strip()
        """The agent's name as given, which is what telemetry and the Logfire UI display.

        Kept verbatim, punctuation and capitals and all: it is what a person recognizes the agent by.
        The variable is keyed on `variable_name`, which is this name normalized, so the display name
        can be changed to read better without moving the agent to a different config -- as long as it
        still normalizes to the same key.
        """
        self.variable_name = variable_name
        """The Logfire variable holding the config: `agent__` plus the normalized name."""
        self.label = label
        """The label resolved, or `None` to let the variable's targeting rules choose."""
        self.on_unmatched: OnUnmatched = on_unmatched
        """The policy `report` applies to a request's issues; see `OnUnmatched`."""

        self._logfire_instance = logfire_instance if logfire_instance is not None else logfire.DEFAULT_LOGFIRE_INSTANCE
        self._framework = framework
        self._report_baseline: BaselinePublication | None = report_baseline
        # Constructed directly rather than through `logfire.var`, which registers in a per-instance
        # registry and raises on a duplicate name: two `AgentControl`s for one agent -- a process that
        # builds its agent per request, a test suite -- are one configuration stated twice, not a
        # conflict, and the variable is the same variable either way.
        self._variable = Variable(
            variable_name,
            type=AgentConfig,
            default=AgentConfig(),
            logfire_instance=self._logfire_instance,
        )

    def __repr__(self) -> str:
        return f'{type(self).__name__}(name={self.name!r}, label={self.label!r})'

    def resolve(self) -> AgentConfig | None:
        """The published config for this agent, or `None` to run the agent exactly as written.

        `None` is every case in which Logfire has nothing to say: no value published for this label,
        no provider configured, a provider that could not be reached, or a stored value this version
        of the contract could not parse. They are one outcome on purpose -- the agent keeps running on
        its code -- and none of them raises, because a managed config that can take an agent down when
        the network wobbles is worse than no managed config at all.

        A value that *is* published is validated leniently: an entry, setting, or section this release
        cannot make sense of is dropped with a warning while everything around it still applies. See
        [`AgentConfig`][logfire.agent_control.AgentConfig].

        Resolve once per run rather than per model request, and apply that one value everywhere in the
        run: it is what lets every span of a run agree on the version that produced it, and it means
        publishing mid-run takes effect on the next run rather than halfway through this one.
        """
        with self.resolution() as resolution:
            return resolution.config

    def resolution(self) -> AbstractContextManager[Resolution]:
        """Resolve the config for one run, and keep the version it came from on everything inside.

        Entering the context sets the resolved label and version as OpenTelemetry baggage, so every
        span and log emitted inside it -- the run span, each model request, each tool call -- carries
        the published version that produced it. That is the difference between Logfire showing "this
        agent has a config" and "this run was the config at version 7, label `canary`", and it is why
        this is a context manager rather than a second getter.

        Resolve once per run rather than per model request, and apply that one value everywhere in
        the run: it is what lets every span of a run agree on the version that produced it, and it
        means publishing mid-run takes effect on the next run rather than halfway through this one.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        with control.resolution() as resolution:
            if resolution.config is not None:
                ...  # apply it, and run the agent inside this block
        ```

        Like [`resolve`][logfire.agent_control.AgentControl.resolve], it never raises: a resolution
        that fails yields a `Resolution` with no config, which means "run the agent as written".
        """
        return self._resolution()

    @contextmanager
    def _resolution(self) -> Generator[Resolution]:
        try:
            resolved = self._variable.get(label=self.label)
        except Exception as exc:
            # The SDK resolves defensively and turns a provider failure into a fallback rather than an
            # exception, so this is the belt to that pair of braces: nothing about reading a config may
            # reach the agent as a crash. There is no resolution to enter, so there is no baggage
            # either -- the run is simply the code-defined agent.
            self._warn_unreadable(exc)
            unread = Resolution(
                config=None,
                label=None,
                version=None,
                reason='other_error',
                variable_name=self.variable_name,
                _reportable=False,
            )
            # Installed even though there is nothing to report: a later hook asking what this run
            # resolved deserves "to nothing", not "you are not in a run".
            with _use_resolution(unread):
                yield unread
            return
        resolution = Resolution(
            config=self._config_of(resolved),
            label=resolved.label,
            version=resolved.version,
            reason=resolved.reason,
            variable_name=self.variable_name,
        )
        # Installed through `use_resolution`, so the scope this block opens is the same scope a later
        # hook re-enters and reads: one resolution per run, reported the same way wherever it is used.
        with _use_resolution(resolution):
            yield resolution

    def _config_of(self, resolved: ResolvedVariable[AgentConfig]) -> AgentConfig | None:
        """The value to apply, or `None` for every way Logfire can have nothing to say."""
        if resolved.reason in ('resolved', 'context_override'):
            return resolved.value
        if resolved.exception is not None:
            self._warn_unreadable(resolved.exception)
        return None

    def _warn_unreadable(self, exc: Exception) -> None:
        warn_dropped(
            f'Failed to read the Logfire managed config for {self.variable_name!r}: {exc}; '
            'running the agent as written.'
        )

    def report(self, *issues: ApplyIssue) -> None:
        """Apply this control's `on_unmatched` policy to everything one request could not apply.

        The apply helpers plan and report nothing; this is where the policy the user configured is
        applied, once, to every section at once. Which is what makes their return value load-bearing:
        an adapter that plans three sections and forgets to report says nothing, visibly, rather than
        duplicating a warning that was already emitted.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        instructions = apply_instructions(blocks, config)
        tools = apply_tool_definitions(request.tools, config, reserved=request.provider_tool_names)
        settings = apply_settings(config, support=SUPPORT)
        control.report(*instructions.issues, *tools.issues, *settings.issues)
        ```

        Reporting after everything is planned is the point of collecting them: `'error'` used to
        raise inside the first section's apply call, so the strictest policy reported the least --
        the other sections were never planned and their issues were never returned. One call raises
        once, naming every issue.

        An adapter whose framework has its own error type translates this without restating a single
        message, because the exception carries them:

        ```python skip-run="true" skip-reason="illustrative-fragment"
        try:
            control.report(*issues)
        except UnmatchedConfigError as exc:
            raise MyFrameworkError(str(exc)) from exc
        ```

        Raises:
            UnmatchedConfigError: naming every issue, when `on_unmatched` is `'error'`.
        """
        report_issues(self.on_unmatched, issues)

    def report_unmatched(self, message: str) -> None:
        """Report something published that this adapter could not apply, as a message.

        [`report`][logfire.agent_control.AgentControl.report] is the channel for anything the core
        planned, and anything an adapter can describe as an
        [`ApplyIssue`][logfire.agent_control.ApplyIssue] -- including a section it cannot reach
        (`'unsupported-section'`) and a setting its provider dropped
        ([`ApplyIssue.dropped_by_provider`][logfire.agent_control.ApplyIssue.dropped_by_provider]).
        This is the same policy for a message with no path to give, and applies it on its own so a
        message is not held back waiting for a request's other sections.

        Write the message the way the helpers do -- what was published, and what was not applied:

        ```python skip-run="true" skip-reason="illustrative-fragment"
        control.report_unmatched(
            f'Managed agent config selects model {config.model!r}, which this framework cannot switch '
            'per request; that section is not applied.'
        )
        ```

        Raises:
            UnmatchedConfigError: with `message`, when `on_unmatched` is `'error'`.
        """
        report_unmatched(self.on_unmatched, message)

    def report_baseline(
        self, baseline: AgentConfig, resolution: Resolution, *, source: BaselineSource = 'code'
    ) -> None:
        """Report the code baseline for this agent, once per process, on one hint span.

        This is how an agent gets a managed config, and how it stays accurate once it has one.
        **Nothing here writes a variable.** Every agent reports what it says in code, and Logfire
        turns that into a config for an agent it has none for, or offers to refresh a stored baseline
        the code has moved on from -- on a person's click, which is what keeps a managed config
        something someone decided to have rather than something a deployment made for them. The span
        carries the whole contract; every attribute on it is documented on `emit_config_hint`.

        The SDK holds a span-write token and no opinion about what is already in the project, which is
        the right split: a client-side create needs variable-management scope it should not need, and
        could not tell an unknown variable from one with nothing published at this label anyway, while
        the platform knows both. It also means no report can ever carry away a value, a label, or a
        rollout someone saved in the Logfire UI -- the failure mode a read-modify-write of a variable's
        `example` has, and cannot be made not to have from the client side.

        Reported **whether or not a config resolved**, which is what makes the second half possible:
        an agent that reported only while unconfigured would go quiet the moment someone configured
        it, and the baseline stored against it would describe the code as it was that day.
        `resolution.reason` is what tells the two apart on the span, which is why the run's resolution
        is a parameter rather than something this resolves for itself -- a second resolve could
        disagree with the one the run is using, and would report a version the agent never ran on.
        What the report carries is always the code and never the managed value, which is what makes a
        diff a diff.

        At most once per process per destination, and the guard is marked *before* the work, so
        concurrent first requests cannot report twice and a failure is not retried by every later run.
        That is also what makes the caller's job easy: call it on every request and let this decide.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        with control.resolution() as resolution:
            control.report_baseline(build_baseline(instructions=blocks, model=model, tools=tools), resolution)
            ...
        ```

        Never raises. It is called from the middle of an agent run, and describing the agent must not
        be what takes that run down, so anything that goes wrong is said once per process and the run
        keeps running.

        Args:
            baseline: What to report, from [`build_baseline`][logfire.agent_control.build_baseline].
            resolution: The run's resolution, from
                [`resolution`][logfire.agent_control.AgentControl.resolution] or
                [`current_resolution`][logfire.agent_control.AgentControl.current_resolution].
            source: Whether `baseline` describes the agent as written or one request that happened to
                come first; see [`BaselineSource`][logfire.agent_control.BaselineSource]. An adapter
                that reads its framework's agent object leaves this at `'code'`. One whose framework
                assembles its prompt or tool list from callables, so that the earliest anything can be
                read is a request, passes `'observed'` and says so, rather than letting a snapshot of
                one request stand in for a description of the code. A new process reports again, so a
                changed deployment updates either kind. It also chooses how much of the baseline is
                reported by default; see the `report_baseline` argument to `AgentControl`.
        """
        try:
            emit_config_hint(
                # The variable's own instance, which is the one scoped to variables and the one whose
                # project would hold the config -- a process serving two projects reports to each.
                logfire_instance=self._variable.logfire_instance,
                variable_name=self.variable_name,
                agent_name=self.name,
                baseline=baseline,
                source=source,
                framework=self._framework,
                # The source is what decides this when nobody said; see `AgentControl.__init__`.
                publication=self._report_baseline or ('structure' if source == 'observed' else 'text'),
                resolution_reason=resolution.reason,
            )
        except Exception as exc:
            # Describing the agent is not supposed to be able to fail: a baseline is a Pydantic model
            # of JSON-shaped fields, so there is no cycle for `json.dumps` to choke on the way there
            # is in the TypeScript core. What is left is the span pipeline, and a report is
            # documentation that no request depends on -- so this stays here, said once per process
            # rather than once per report, and the caller's request keeps going.
            warn_dropped(
                f'Failed to report the code baseline for Logfire managed variable {self.variable_name!r}: {exc}'
            )

    def current_resolution(self) -> Resolution | None:
        """This agent's resolution for the surrounding run scope, or `None` outside one.

        Sugar over [`current_resolution`][logfire.agent_control.current_resolution] for this control's
        own variable, which is what an adapter almost always wants: it holds the control already, and
        it should not have to know that the scope is keyed on a variable name.
        """
        return current_resolution(self.variable_name)


_current_resolutions: ContextVar[Mapping[str, Resolution]] = ContextVar('logfire.agent_control_resolutions', default={})
"""The resolutions in scope, per variable, for the current task.

A mapping rather than one value because agents nest: a handoff, a subagent, or a tool that runs
another managed agent puts a second control's scope inside the first, and `current_resolution` for
either of them has to keep answering about *that* one rather than about whichever was entered last.
"""


def use_resolution(resolution: Resolution) -> AbstractContextManager[None]:
    """Make one resolution the answer for its agent, and report it, for the whole of a block.

    The seam for a framework that resolves in one place and does the work in another. An adapter with
    one hook around the run does not need it -- [`AgentControl.resolution`][logfire.agent_control.AgentControl.resolution]
    already is that scope -- but an adapter whose framework hands it two hooks per run, an instruction
    callable and a model wrapper, has to make them agree. Resolving in each of them means a value
    published between the two, or a rollout that lands differently on two reads, can send prompt A
    with model B while the telemetry attributes the request to B alone. Resolving once and installing
    it here means both hooks read the same value:

    ```python skip-run="true" skip-reason="illustrative-fragment"
    with control.resolution() as resolution:  # already installs it for the block it wraps
        ...


    # ... or, where the run seam and the request seam are different callbacks:
    def on_run_start():
        resolution = ...  # resolved once, carried in the framework's own per-run state
        return use_resolution(resolution)  # entered for the rest of the run


    def before_request():
        resolution = control.current_resolution()  # the same one, in both hooks
    ```

    Entering also re-establishes the resolution's telemetry, exactly as
    [`Resolution.reported`][logfire.agent_control.Resolution.reported] does, so spans inside the block
    carry the label and version that produced them. Nesting is fine: an inner scope shadows an outer
    one for that agent and the outer one comes back on exit.

    The **unit of resolution** is a decision each adapter documents, because frameworks differ in what
    they offer. Where there is a run seam -- something that brackets a whole agent run -- resolve once
    per run, so every span of the run agrees on the version that produced it and a value published
    mid-run takes effect on the next run. Where there is only a per-model-request hook, resolution is
    per request, and a rollout can move between two requests of one run. Both are supportable; what is
    not is implying the first while doing the second.
    """
    return _use_resolution(resolution)


@contextmanager
def _use_resolution(resolution: Resolution) -> Generator[None]:
    token = _current_resolutions.set({**_current_resolutions.get(), resolution.variable_name: resolution})
    try:
        with resolution.reported():
            yield
    finally:
        _current_resolutions.reset(token)


def current_resolution(variable_name: str) -> Resolution | None:
    """The resolution installed for `variable_name` by the innermost enclosing scope, if any.

    `None` means no scope is open for that agent here -- an adapter's hook reached outside a run, or a
    run that never resolved -- which is not an error: it means the same thing an unresolved config
    does, run the agent as written.
    """
    return _current_resolutions.get().get(variable_name)
