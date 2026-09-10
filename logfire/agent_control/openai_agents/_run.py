"""One resolution, and everything else one run of one managed agent shares between the SDK's hooks.

The SDK hands this adapter two hooks per model request and no way to pass anything between them: the
runner renders `Agent.instructions` in a task of its own (`gather_with_cancel`), so nothing the
renderer records reaches the model wrapper a moment later, and the model is handed the assembled
prompt and never the run context. Resolving in each hook is what the contract forbids -- a publish or
a probabilistic rollout landing between the two sends prompt A with model and tools B, while the
telemetry attributes the request to B alone.

`Agent.get_all_tools` is the seam that closes it. The runner awaits it directly, in the coroutine that
then renders the prompt and calls the model, so a context variable set there is visible to *both*
hooks -- and it is handed the run's `RunContextWrapper`, which is the run's identity. So a managed
agent resolves there, once per run, and both hooks read that one `Resolution` back out. Everything
else a run has to keep to itself rather than share with the concurrent runs of the same agent -- which
keys a per-run `RunConfig(model_settings=...)` set explicitly, which models this run has resolved --
lives on the same record, for the same reason.
"""

from __future__ import annotations

import weakref
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from agents import RunContextWrapper
from agents.models.interface import Model

from .. import AgentControl, Resolution

_current_runs: ContextVar[Mapping[AgentControl, Run]] = ContextVar(
    'logfire_agent_control_openai_agents_runs', default={}
)
"""The run in progress, per wrapped agent, for the current task.

A mapping rather than one value because agents nest: a handoff, or a tool that runs another managed
agent, puts a second agent's run inside the first, and each of them has to keep answering about its
own. Concurrent runs of one agent are in tasks of their own, each with its own copy of this.

Keyed on the `AgentControl` itself rather than on the variable it reads, because one variable can
have more than one reader: wrapping an agent again for another label is exactly what the second
argument to `agent_control` is for, and a handoff between two such wrappers runs both of them under
one `RunContextWrapper`. Keyed by name, the second would find the first's record and apply the first
label's config. The two hooks that read this -- the prompt renderer and the model wrapper -- are
handed the same `AgentControl` object, so identity is the exact key for both.
"""


@dataclass
class Run:
    """What one run of one managed agent knows that its per-request hooks cannot work out alone."""

    resolution: Resolution
    """The one value this whole run applies; see the module docstring."""
    context: weakref.ReferenceType[RunContextWrapper[Any]]
    """A weak reference to the run's context, which is what identifies the run this record is for."""
    explicit_settings: frozenset[str] = frozenset[str]()
    """The `ModelSettings` fields a per-run `RunConfig(model_settings=...)` set explicitly.

    Captured where the SDK merges that override into the agent's own settings, which is the only place
    the two are still distinguishable: by the time a model sees them there is one object and no record
    of who set what, and a run that passes the value the code already had is invisible in it. That is
    the case the contract's precedence turns on -- code `0.2`, published `0.8`, and a run explicitly
    passing `0.2` has to stay `0.2` -- so it is captured rather than inferred.
    """
    models: list[Model] = field(default_factory=list[Model])
    """The models this run has actually made a request through, in order.

    The runner tells the *wrapper* that a run ended, and a wrapper that handed the request to another
    model has to pass that on to the right one. A wrapper is shared by every concurrent run of its
    agent, so which model a run used is the run's own business: consulting the last request's model
    would clean up after, or ask for retry advice from, whichever run happened to go last.
    """

    def used(self, model: Model) -> None:
        """Record that this run made a request through `model`."""
        if not any(used is model for used in self.models):
            self.models.append(model)


def current_run(control: AgentControl) -> Run | None:
    """The run in progress for `control` here, or `None` outside one.

    `None` is not an error: it means the managed prompt or the managed model was reached outside the
    seam that opens a run -- something calling the model wrapper directly, say -- and the caller
    resolves for itself instead.

    A record outlives the run that opened it, since the SDK offers nowhere to close it: the next run
    in that task replaces it, and until then a lifecycle call the runner makes after the run has ended
    still finds the run it belongs to, which is exactly what it is for.
    """
    return _current_runs.get().get(control)


def resolve(control: AgentControl) -> Resolution:
    """One reading of `control`, as a value to carry rather than a block to stay inside.

    The core's `resolution()` is a context manager because the usual adapter resolves and runs the
    agent inside it. This one cannot: the seam that resolves returns, and the hooks that apply the
    value run after it. So the block is left immediately and the `Resolution` is carried on the run's
    record, and each hook re-establishes its telemetry with `use_resolution` for its own work -- which
    is what the core's `Resolution.reported` exists for.
    """
    with control.resolution() as resolution:
        return resolution


def begin_run(control: AgentControl, context: RunContextWrapper[Any]) -> Run:
    """The record for the run `context` identifies, resolving once for it the first time.

    Called at the top of every turn, because that is where the SDK's seam is, and answering with the
    same record every time is what makes resolution once per *run*: every turn applies the version the
    run started on, and a value published mid-run takes effect on the next run rather than between two
    turns of this one.

    Records whose run context has been collected are dropped on the way past. Nothing else ever
    removes one -- a record deliberately outlives its run, because the runner makes lifecycle calls
    after the run has ended -- so a task that wraps a fresh agent per request, which the docs ask you
    not to do but nothing prevents, would otherwise grow this mapping for as long as it lives. A
    context is reachable for exactly as long as something can still ask about that run, since the
    `RunResult` holds it, so this frees a record no later than the run it belongs to.
    """
    runs = {wrapped: run for wrapped, run in _current_runs.get().items() if run.context() is not None}
    run = runs.get(control)
    if run is not None and run.context() is context:
        return run
    run = Run(resolution=resolve(control), context=weakref.ref(context))
    _current_runs.set({**runs, control: run})
    return run
