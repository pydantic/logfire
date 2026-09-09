"""Back an agent's Agent Control configuration with one Logfire variable."""

from __future__ import annotations

import json
import threading
import warnings
from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias

import logfire
from logfire.variables import ResolutionReason, ResolvedVariable, Variable, VariableAlreadyExistsError
from logfire.variables.abstract import NoOpVariableProvider, VariableProvider

from ._config import AgentConfig
from ._names import agent_variable_name
from ._reporting import OnUnmatched, report_unmatched, warn_dropped
from ._schema import AGENT_CONFIG_JSON_SCHEMA

if TYPE_CHECKING:
    from logfire import Logfire

BaselineSource: TypeAlias = Literal['code', 'observed']
"""Where a published baseline came from, which an adapter has to say because it changes what it means.

- `'code'` is the agent *as written*: read off the agent object, its declared prompts, its declared
  settings, its tool definitions. It describes every request the agent will make.
- `'observed'` is one request, snapshotted because the framework offers nothing to read the agent
  from until it runs. It describes the request it came from and nothing else, so a prompt or a tool
  list assembled from the run's own input is a sample rather than a description -- and text that came
  from a request is one tenant's, one user's, one retrieved document's, published into a variable
  every member of the Logfire project can read.

The distinction is not cosmetic: an adapter that can only observe should mark blocks it did not find
in code as dynamic rather than publishing their rendered text, and the editor has to be able to tell
a description of the code from a description of one request that happened first.
"""

# Destinations handed to a baseline publisher in this process. Marking before the thread starts
# prevents concurrent first requests from scheduling duplicate work, and means a failure is not
# retried by every later request.
_baseline_publish_attempted: set[tuple[Logfire, str]] = set()
_baseline_publish_lock = threading.Lock()


def reset_baseline_publish_guard() -> None:
    """Clear the once-per-process baseline publishing state. Intended for tests only."""
    with _baseline_publish_lock:
        _baseline_publish_attempted.clear()


def _spawn_baseline_publish(variable: Variable[AgentConfig], example: str, source: BaselineSource) -> threading.Thread:
    """Move the provider read and targeted write off the request's thread."""
    thread = threading.Thread(target=_publish_baseline, args=(variable, example, source), daemon=True)
    thread.start()
    return thread


_BASELINE_DESCRIPTIONS: Mapping[BaselineSource, str] = {
    'code': (
        'Agent Control config for this agent. The example is the agent as written, published by the SDK; '
        'set a value here to change what the agent sends, and remove it to go back to the code.'
    ),
    'observed': (
        'Agent Control config for this agent. The example was snapshotted from one request, because this '
        'framework offers nothing to read the agent from until it runs, so it describes that request rather '
        'than every one. Set a value here to change what the agent sends, and remove it to go back to the code.'
    ),
}
"""What a newly created variable says about itself, which depends on what its example actually is."""


def _publish_baseline(variable: Variable[AgentConfig], example: str, source: BaselineSource) -> None:
    """Create the variable from the baseline, or update only the `example` on the one that exists.

    Creation is what makes Logfire the editing surface without a create-in-UI step: the stored schema
    is the contract's, not the one a Pydantic version happens to emit, and the baseline rides along as
    the `example` so the editor opens on what the agent does today rather than on a blank form.

    Updating an existing variable is read-modify-write, because the provider offers nothing narrower:
    `update_variable` PUTs the whole definition to `/v1/variables/{name}/` and takes no revision or
    `If-Match` input. Everything a client can do to narrow that window is done here, and it is worth
    being exact about what is and is not left:

    - The variable is only ever *created* when the read says it is missing, so the common case for a
      new agent involves no overwrite at all.
    - An existing variable is re-read immediately before the write, and the object written is that
      *fresh* read with `example` replaced -- never one read earlier, and never one a caller passed
      in. Whatever the UI saved up to that read is preserved: values, labels, rollout, description.
    - The write is skipped entirely when the fresh read already carries this `example`, which is the
      steady state for a deployed agent, so the overwhelmingly common outcome is no write.
    - It runs at most once per process per variable, off the request thread.

    What remains is one HTTP round trip: a value or label saved in the Logfire UI *between* the fresh
    read returning and the write landing is overwritten by the older state that read returned, and the
    UI reports success for the publish it just lost. There is nothing further the client side can do
    about it -- closing it needs an example-only PATCH, or a conditional write on a revision or ETag,
    on the platform API: https://github.com/pydantic/pydantic-ai-harness/issues/565. Until then, a
    deployment that cannot tolerate that window sets `publish_baseline=False` and creates the variable
    in the UI. A successful baseline write is *not* evidence that managed values survived it.

    Every outcome is reported through the Logfire instance the variable belongs to: creation writes a
    persistent, teammate-visible object into the user's project, so it belongs where they are already
    looking rather than in a `warnings.warn` raised on a daemon thread that no one sees. The failure
    keeps the warning as well, for local development that exports nowhere.
    """
    logfire_instance = variable.logfire_instance
    provider = logfire_instance.config.get_variable_provider()
    try:
        if provider.get_variable_config(variable.name) is None:
            if isinstance(provider, NoOpVariableProvider):
                # No provider is configured, so there is nowhere to create anything. That is the
                # local-development default rather than a failure, and the agent runs on its code.
                return
            provider.create_variable(
                variable.to_config().model_copy(
                    update={
                        'json_schema': AGENT_CONFIG_JSON_SCHEMA,
                        'example': example,
                        'description': _BASELINE_DESCRIPTIONS[source],
                    }
                )
            )
            logfire_instance.info(
                'Created Logfire managed variable {variable_name} from the {baseline_source} baseline; '
                'set a value in Logfire to manage this agent from there',
                variable_name=variable.name,
                baseline_source=source,
            )
        else:
            _update_example(provider, variable.name, example)
    except VariableAlreadyExistsError:
        # The variable already exists server-side (another process or the UI created it first).
        pass
    except Exception as exc:
        logfire_instance.warn(
            'Failed to publish the code baseline for Logfire managed variable {variable_name}',
            variable_name=variable.name,
            _exc_info=True,
        )
        warnings.warn(f'Failed to publish the code baseline for Logfire managed variable {variable.name!r}: {exc}')


def _update_example(provider: VariableProvider, name: str, example: str) -> None:
    """Write `example` onto the variable's current definition, read as late as possible.

    Deliberately its own read rather than reusing the one that decided the variable exists: the value
    written back is the whole variable definition, so every moment between reading it and writing it
    is a moment in which someone else's edit can be inside the object about to be overwritten. Taking
    the read here makes that window one round trip instead of two, and makes "never write from a
    config read earlier" a property of the code rather than a rule to remember.
    """
    config = provider.get_variable_config(name)
    if config is None or config.example == example:
        # Vanished between the two reads, or already carries this baseline. Either way there is
        # nothing to write, and re-creating a variable someone just deleted is not this thread's call.
        return
    provider.update_variable(name, config.model_copy(update={'example': example}))


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
    and publishes the code baseline the Logfire editor diffs against. What a published value *does* to
    a request lives in the pure helpers -- [`apply_instructions`][logfire.agent_control.apply_instructions],
    [`apply_tool_definitions`][logfire.agent_control.apply_tool_definitions], and
    [`apply_settings`][logfire.agent_control.apply_settings] -- so an adapter for any agent framework
    is this object plus the framework's own per-request hook:

    ```python
    from logfire.agent_control import AgentControl, Block, apply_instructions, build_baseline

    control = AgentControl('checkout_assistant', label='production')
    control.publish_baseline(build_baseline(instructions=[Block('You are a checkout assistant.', id='agent')]))

    config = control.resolve()
    if config is not None:
        blocks = apply_instructions([Block('You are a checkout assistant.', id='agent')], config).blocks
    ```

    Nothing published can crash a request. An unreachable provider, a missing value, or one this
    version of the contract cannot parse leaves `resolve()` returning `None`, which means "run the
    agent as written"; beyond that, a value the contract can't act on costs only the piece containing
    it -- one setting, one tool, one block -- and warns once per process.
    """

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        logfire_instance: Logfire | None = None,
        on_unmatched: OnUnmatched = 'warn',
        publish_baseline: bool = True,
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
            logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
                global one, which is what `logfire.configure()` sets up.
            on_unmatched: The default policy for published entries that reach nothing, carried here so
                an adapter can read it off the control it was handed rather than plumbing a second
                argument through its hooks. Nothing in this class applies it; the pure helpers take it
                per call. See [`OnUnmatched`][logfire.agent_control.OnUnmatched].
            publish_baseline: Whether `publish_baseline()` actually writes. Enabled by default because
                the baseline is documentation for the Logfire editor and is never resolved or applied
                to a request, so a failed or stale publish cannot change agent behavior. Disable it
                when the variables token is intentionally read-only, or when code must not write
                variable metadata.
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
        """The policy an adapter should pass to the pure helpers; see `OnUnmatched`."""

        self._logfire_instance = logfire_instance if logfire_instance is not None else logfire.DEFAULT_LOGFIRE_INSTANCE
        self._publish_baseline = publish_baseline
        self._publish_thread: threading.Thread | None = None
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

    def report_unmatched(self, message: str) -> None:
        """Report something published that this adapter could not apply, under `on_unmatched`.

        The pure helpers report what *they* could not apply -- an instruction id no block carries, a
        tool override no tool matches, a settings key the contract has no field for. This is the same
        policy for what only the adapter can know: a `model` section on a framework that cannot switch
        models at request time, a section its hook does not reach. It exists so an adapter reports
        those through the policy the user configured rather than reimplementing it, and so every gap
        between what Logfire shows and what the agent does sounds the same.

        Write the message the way the helpers do -- what was published, and what was not applied:

        ```python skip-run="true" skip-reason="illustrative-fragment"
        control.report_unmatched(
            f'Managed agent config selects model {config.model!r}, which this framework cannot switch '
            'per request; that section is not applied.'
        )
        ```

        Raises:
            ValueError: with `message`, when `on_unmatched` is `'error'`.
        """
        report_unmatched(self.on_unmatched, message)

    def publish_baseline(self, baseline: AgentConfig, *, source: BaselineSource = 'code') -> threading.Thread | None:
        """Publish a baseline as the variable's `example`, creating the variable if needed.

        Call this once the adapter can describe the agent. It runs at most once per process per
        variable, off the calling thread, and it is marked as attempted *before* the work starts, so
        a failure does not retry on every later request and concurrent first requests do not schedule
        the same write twice.

        Args:
            baseline: What to publish, from
                [`build_baseline`][logfire.agent_control.build_baseline].
            source: Whether `baseline` describes the agent as written or one request that happened to
                come first; see [`BaselineSource`][logfire.agent_control.BaselineSource]. An adapter
                that reads its framework's agent object leaves this at `'code'`. One whose framework
                assembles its prompt or tool list from callables, so that the earliest anything can be
                read is a request, passes `'observed'` and says so, rather than letting a snapshot of
                one request stand in for a description of the code. A new process publishes again, so
                a changed deployment updates either kind.

        Returns:
            The daemon thread doing the write, or `None` when nothing was scheduled -- publishing is
            disabled, or this variable was already published to in this process. Join it if the
            process may exit before a background write completes; ignore it otherwise.
        """
        if not self._publish_baseline:
            return None
        example = json.dumps(baseline.model_dump(exclude_none=True), indent=2)
        key = (self._logfire_instance, self.variable_name)
        with _baseline_publish_lock:
            if key in _baseline_publish_attempted:
                return None
            _baseline_publish_attempted.add(key)
        self._publish_thread = _spawn_baseline_publish(self._variable, example, source)
        return self._publish_thread

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
