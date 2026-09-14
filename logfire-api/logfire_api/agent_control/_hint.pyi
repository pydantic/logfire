from ._config import AgentConfig as AgentConfig, InstructionBlock as InstructionBlock, ParameterOverride as ParameterOverride, ToolDefinitionOverride as ToolDefinitionOverride
from ._schema import SCHEMA_SHA256 as SCHEMA_SHA256, canonical_json as canonical_json
from _typeshed import Incomplete
from logfire import Logfire as Logfire
from logfire.variables import ResolutionReason as ResolutionReason
from typing import Any, TypeAlias

BaselineSource: TypeAlias
BaselinePublication: TypeAlias
BaselineReduction: TypeAlias
CONFIG_HINT_SPAN_NAME: str
CONFIG_HINT_MESSAGE: str
DEFAULT_FRAMEWORK: str
MAX_BASELINE_BYTES: Incomplete

def reset_config_hint_guard() -> None:
    """Clear the once-per-process report guard. Intended for tests only."""
def structure_only(baseline: AgentConfig) -> AgentConfig:
    """The same baseline with every piece of model-facing text taken out, and every seam kept.

    What `'structure'` publication means, applied to a built baseline: an instruction entry keeps its
    `id` and its `dynamic` flag and loses its text, a tool keeps its name, its toolset, and the names
    of its parameters and loses every description. The editor can still address everything it could
    address before -- which is what separates this from `'off'` -- and simply has nothing to show for
    what the code says.

    An entry with no `id` is dropped rather than emptied. Its text was the only thing it carried and
    the only thing that could be published under `'structure'` is a seam, so what would be left is an
    entry naming nothing, which an editor can neither show nor offer an override for.
    """
def serialize_baseline(baseline: AgentConfig, publication: BaselinePublication) -> tuple[str | None, BaselineReduction, int]:
    '''Serialize a baseline to fit `MAX_BASELINE_BYTES`, dropping whole sections when it does not.

    Returns the JSON to put on the hint span (`None` when even the reduced baseline does not fit),
    which reduction was applied, and the baseline\'s size in UTF-8 bytes before any of it.

    Reduction drops `tool_definitions` first and then gives up, rather than trimming text to a budget.
    The contract already bounds a single instruction block, so a baseline this large is one with an
    unbounded *number* of things in it, and tool definitions are where that goes: every advertised
    tool, its description, and an entry per parameter. They are also the section a config needs least
    -- the editor can offer a tool override without one, while a baseline with no instructions has
    nothing to show at all. Either way the result is a whole, valid `AgentConfig` and the reduction is
    named on the span, so a consumer reads a baseline that is complete or knowingly partial, never one
    that parses into something the agent does not do.

    `\'off\'` lands in the same place a baseline too large to carry does, and says so the same way:
    there is one state on the span for "the document is not here", and a second word for it would
    only be a second thing for a consumer to learn.
    '''
def dump_baseline(baseline: AgentConfig) -> str:
    """The baseline as the JSON a hint carries, indented the way a variable's `example` is read."""
def baseline_sha256(baseline: AgentConfig) -> str:
    '''The digest that says whether two reports describe the same agent.

    Always over the *whole* reported baseline, never over the JSON the span ended up carrying. A
    baseline too large for a span attribute is reported with its tool definitions dropped, or with no
    baseline at all, and a digest taken after that would change when nothing about the agent had --
    and would leave every oversize report looking like every other one, which is the case that has
    nothing else to tell it apart by.

    "Reported" rather than "built" is the load-bearing word under `\'structure\'`: the stripped baseline
    *is* this deployment\'s baseline rather than a redaction of a fuller one, so two deployments running
    the same code under the same policy agree with each other. Under `\'off\'`, where nothing is carried
    at all, it is the built baseline, so a report still says whether the code has moved.

    Which makes this the digest of a document the span does not always carry: a consumer compares it
    with another hint\'s, and verifies it against `agent_control.baseline` only when
    `agent_control.baseline_reduction` is `\'none\'`.

    Over [`canonical_json`][logfire.agent_control.canonical_json], which is the same canonical form
    `SCHEMA_SHA256` uses, so an adapter computing a digest of its own agrees with this one and a
    baseline whose first instruction block has an accent in it does not digest differently in two
    languages.
    '''
def deployment_attributes(instance: Logfire) -> dict[str, Any]:
    """Which deployment reported a baseline, from what the Logfire instance already knows.

    The variable a config lives in is derived from the agent's name alone, so two services that each
    define a `checkout_assistant` land on one `agent__checkout_assistant` -- and so do the same
    service's dev and prod deployments, since a variable is one value per project and the dev/prod
    split is its labels. Without this a consumer cannot tell whose code it is looking at. The resource
    attributes on the span carry some of it, but a contract the platform indexes has to say what it
    promises, and OTel resource attributes are not something this span has promised.

    Read off the instance the hint is emitted on rather than configured here: a process serving two
    Logfire projects configures each separately, and asking the user to restate a service name they
    already gave `logfire.configure()` is a second place for the two to disagree. `service_version` is
    whatever Logfire resolved for the running code, which is the current commit when the process runs
    in a git checkout and has not been told otherwise.

    Anything the SDK does not know is left off rather than sent as an empty string: absent is a state
    a consumer can act on, where `''` is a value it has to learn to disbelieve.
    """
def emit_config_hint(*, logfire_instance: Logfire, variable_name: str, agent_name: str, baseline: AgentConfig, source: BaselineSource, framework: str, publication: BaselinePublication, resolution_reason: ResolutionReason) -> None:
    """Report one agent's code baseline, at most once per process per destination.

    This is how an agent gets a managed config, and how it stays accurate once it has one. The SDK
    writes no variable: every agent reports what it says in code, and Logfire turns that into a config
    for an agent it has none for, or offers to refresh a stored baseline the code has moved on from --
    on a person's click, which is what keeps a managed config something someone decided to have rather
    than something a deployment made for them.

    The span is named `agent_control_config_hint` and carries:

    - `agent_control.variable_name` -- the `agent__<key>` variable the config belongs in.
    - `agent_control.agent_name` -- the agent's name as written in code. The variable name is derived
      from it lossily, so this is what says *which* agent landed on that key. An SDK whose adapter can
      be pointed at a variable without an agent having a name of its own leaves it off rather than
      sending null; this core always has one, because a name is what an `AgentControl` is built on.
    - `agent_control.framework` -- which Agent Control SDK produced the hint; see `DEFAULT_FRAMEWORK`.
    - `agent_control.baseline_source` -- `'code'` or `'observed'`; see
      [`BaselineSource`][logfire.agent_control.BaselineSource].
    - `agent_control.schema_sha256` -- the contract schema this baseline was built against, so a
      consumer stores the matching JSON schema on the variable rather than guessing, and can tell a
      baseline from an older SDK from one it wrote the schema for.
    - `agent_control.baseline` -- the `AgentConfig` snapshot, as the JSON a variable's `example` holds.
      Absent when `agent_control.baseline_reduction` is `'omitted'`.
    - `agent_control.baseline_reduction` -- `'none'`, `'tool_definitions'`, or `'omitted'`: what the
      baseline had to give up to fit `MAX_BASELINE_BYTES`. Always present, so a partial baseline is
      partial on the record rather than by inference.
    - `agent_control.baseline_bytes` -- the reported baseline's UTF-8 size before any reduction.
    - `agent_control.baseline_sha256` -- the digest of the whole reported baseline, taken before any
      reduction, so two reports of the same code agree and two oversize reports of different code do
      not. A consumer verifies it against `agent_control.baseline` only when the reduction is `'none'`.
    - `agent_control.service_name`, `agent_control.environment`, `agent_control.service_version` --
      which deployment reported it; see `deployment_attributes`. Each is left off when the Logfire
      instance does not know it.
    - `agent_control.resolution_reason` -- how this agent's variable resolved (`'resolved'`,
      `'code_default'`, ...). Since every agent reports, the span's existence no longer says whether
      one had a config, and this is the fact a consumer needs to tell a baseline that wants a config
      created from it from one that may only be refreshing a stale example.

    There is deliberately no attribute saying which
    [`BaselinePublication`][logfire.agent_control.BaselinePublication] a report was made under. A
    baseline is whatever the deployment's policy says it is: `baseline_sha256` and `baseline_bytes`
    describe what was actually reported, so two deployments running the same code under the same
    policy agree, and a consumer never has to reconstruct what a fuller report would have said.

    Attributes rather than one nested blob because the hint is a contract with a consumer that queries
    it: a name it filters on and a size it can threshold have to be columns, and the baseline is the
    only one of them that is a document.

    A span rather than a log record, deliberately: a log below the configured `min_level` is dropped
    before it is exported, and a signal the platform contract depends on cannot be something a
    project's logging configuration silently withholds. It takes no time, so it opens and closes on
    the spot.

    The guard is marked *before* the work, so concurrent first requests cannot report twice and a
    failure is not retried by every later run. Which is also what makes the caller's job easy: call it
    on every request and let this decide.
    """
