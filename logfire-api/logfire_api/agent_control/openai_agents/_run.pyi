import weakref
from .. import AgentControl as AgentControl, Resolution as Resolution
from agents import RunContextWrapper
from agents.models.interface import Model
from collections.abc import Mapping as Mapping
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Run:
    """What one run of one managed agent knows that its per-request hooks cannot work out alone."""
    resolution: Resolution
    context: weakref.ReferenceType[RunContextWrapper[Any]]
    explicit_settings: frozenset[str] = ...
    models: list[Model] = field(default_factory=list[Model])
    def used(self, model: Model) -> None:
        """Record that this run made a request through `model`."""

def current_run(control: AgentControl) -> Run | None:
    """The run in progress for `control` here, or `None` outside one.

    `None` is not an error: it means the managed prompt or the managed model was reached outside the
    seam that opens a run -- something calling the model wrapper directly, say -- and the caller
    resolves for itself instead.

    A record outlives the run that opened it, since the SDK offers nowhere to close it: the next run
    in that task replaces it, and until then a lifecycle call the runner makes after the run has ended
    still finds the run it belongs to, which is exactly what it is for.
    """
def resolve(control: AgentControl) -> Resolution:
    """One reading of `control`, as a value to carry rather than a block to stay inside.

    The core's `resolution()` is a context manager because the usual adapter resolves and runs the
    agent inside it. This one cannot: the seam that resolves returns, and the hooks that apply the
    value run after it. So the block is left immediately and the `Resolution` is carried on the run's
    record, and each hook re-establishes its telemetry with `use_resolution` for its own work -- which
    is what the core's `Resolution.reported` exists for.
    """
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
