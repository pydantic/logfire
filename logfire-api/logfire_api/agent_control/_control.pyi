import threading
from ._config import AgentConfig as AgentConfig
from ._names import agent_variable_name as agent_variable_name
from ._reporting import OnUnmatched as OnUnmatched, report_unmatched as report_unmatched, warn_dropped as warn_dropped
from ._schema import AGENT_CONFIG_JSON_SCHEMA as AGENT_CONFIG_JSON_SCHEMA
from _typeshed import Incomplete
from contextlib import AbstractContextManager
from dataclasses import dataclass
from logfire import Logfire as Logfire
from logfire.variables import ResolutionReason as ResolutionReason, ResolvedVariable as ResolvedVariable, Variable as Variable, VariableAlreadyExistsError as VariableAlreadyExistsError
from logfire.variables.abstract import NoOpVariableProvider as NoOpVariableProvider, VariableProvider as VariableProvider
from typing import TypeAlias

BaselineSource: TypeAlias

def reset_baseline_publish_guard() -> None:
    """Clear the once-per-process baseline publishing state. Intended for tests only."""

BASELINE_PUBLISH_THREAD_PREFIX: str

@dataclass(frozen=True)
class Resolution:
    """One reading of an agent's managed config, and which published version it came from.

    The config is what to apply; the rest is what to say about it. A run that reports the label and
    version it resolved is what lets the Logfire UI tell a wired-up agent from one that merely has a
    config, and lets a regression be traced back to the version that produced it.
    """
    config: AgentConfig | None
    label: str | None
    version: int | None
    reason: ResolutionReason
    variable_name: str
    def reported(self) -> AbstractContextManager[None]:
        '''Put this resolution\'s label and version back on the spans of a later block.

        [`AgentControl.resolution`][logfire.agent_control.AgentControl.resolution] already does this
        for the block it wraps, which is all an adapter needs when one hook spans the run. An adapter
        whose framework resolves in one place and runs the model in another -- a graph node that
        cannot hold a context open across the nodes after it -- reads the resolution once, carries it
        in the framework\'s own state, and wraps each later block in this, so every span of the run
        still says which published version produced it.

        ```python skip-run="true" skip-reason="illustrative-fragment"
        with resolution.reported():
            ...  # spans emitted here carry the resolved label and version
        ```

        Re-entrant and safe to use concurrently: each block establishes its own context rather than
        sharing one. It does nothing when there was no resolution to report, so an adapter does not
        have to branch on that.
        '''

class AgentControl:
    '''Manage one agent\'s config through its `agent__<name>` Logfire variable.

    The variable holds an [`AgentConfig`][logfire.agent_control.AgentConfig]. Each present section --
    `instructions`, `model`, `settings`, or `tool_definitions` -- is managed from Logfire, while an
    absent section keeps the code-defined behavior. Removing a section in Logfire deliberately reverts
    that section to code. There is no third state.

    This class owns the transport, and nothing else: it names the variable, reads the published value,
    and publishes the code baseline the Logfire editor diffs against. What a published value *does* to
    a request lives in the pure helpers -- [`apply_instructions`][logfire.agent_control.apply_instructions],
    [`apply_tool_definitions`][logfire.agent_control.apply_tool_definitions], and
    [`apply_settings`][logfire.agent_control.apply_settings] -- so an adapter for any agent framework
    is this object plus the framework\'s own per-request hook:

    ```python
    from logfire.agent_control import AgentControl, Block, apply_instructions, build_baseline

    control = AgentControl(\'checkout_assistant\', label=\'production\')
    control.publish_baseline(build_baseline(instructions=[Block(\'You are a checkout assistant.\', id=\'agent\')]))

    config = control.resolve()
    if config is not None:
        blocks = apply_instructions([Block(\'You are a checkout assistant.\', id=\'agent\')], config).blocks
    ```

    Nothing published can crash a request. An unreachable provider, a missing value, or one this
    version of the contract cannot parse leaves `resolve()` returning `None`, which means "run the
    agent as written"; beyond that, a value the contract can\'t act on costs only the piece containing
    it -- one setting, one tool, one block -- and warns once per process.
    '''
    name: Incomplete
    variable_name: Incomplete
    label: Incomplete
    on_unmatched: OnUnmatched
    def __init__(self, name: str, *, label: str | None = None, logfire_instance: Logfire | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True) -> None:
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
    def resolution(self) -> AbstractContextManager[Resolution]:
        '''Resolve the config for one run, and keep the version it came from on everything inside.

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
        '''
    def report_unmatched(self, message: str) -> None:
        '''Report something published that this adapter could not apply, under `on_unmatched`.

        The pure helpers report what *they* could not apply -- an instruction id no block carries, a
        tool override no tool matches, a settings key the contract has no field for. This is the same
        policy for what only the adapter can know: a `model` section on a framework that cannot switch
        models at request time, a section its hook does not reach. It exists so an adapter reports
        those through the policy the user configured rather than reimplementing it, and so every gap
        between what Logfire shows and what the agent does sounds the same.

        Write the message the way the helpers do -- what was published, and what was not applied:

        ```python skip-run="true" skip-reason="illustrative-fragment"
        control.report_unmatched(
            f\'Managed agent config selects model {config.model!r}, which this framework cannot switch \'
            \'per request; that section is not applied.\'
        )
        ```

        Raises:
            ValueError: with `message`, when `on_unmatched` is `\'error\'`.
        '''
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
    def current_resolution(self) -> Resolution | None:
        """This agent's resolution for the surrounding run scope, or `None` outside one.

        Sugar over [`current_resolution`][logfire.agent_control.current_resolution] for this control's
        own variable, which is what an adapter almost always wants: it holds the control already, and
        it should not have to know that the scope is keyed on a variable name.
        """

def use_resolution(resolution: Resolution) -> AbstractContextManager[None]:
    '''Make one resolution the answer for its agent, and report it, for the whole of a block.

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
        resolution = ...  # resolved once, carried in the framework\'s own per-run state
        return use_resolution(resolution)  # entered for the rest of the run


    def before_request():
        resolution = control.current_resolution()  # the same one, in both hooks
    ```

    Entering also re-establishes the resolution\'s telemetry, exactly as
    [`Resolution.reported`][logfire.agent_control.Resolution.reported] does, so spans inside the block
    carry the label and version that produced them. Nesting is fine: an inner scope shadows an outer
    one for that agent and the outer one comes back on exit.

    The **unit of resolution** is a decision each adapter documents, because frameworks differ in what
    they offer. Where there is a run seam -- something that brackets a whole agent run -- resolve once
    per run, so every span of the run agrees on the version that produced it and a value published
    mid-run takes effect on the next run. Where there is only a per-model-request hook, resolution is
    per request, and a rollout can move between two requests of one run. Both are supportable; what is
    not is implying the first while doing the second.
    '''
def current_resolution(variable_name: str) -> Resolution | None:
    """The resolution installed for `variable_name` by the innermost enclosing scope, if any.

    `None` means no scope is open for that agent here -- an adapter's hook reached outside a run, or a
    run that never resolved -- which is not an error: it means the same thing an unresolved config
    does, run the agent as written.
    """
