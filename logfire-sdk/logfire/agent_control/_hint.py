"""The span an agent reports its code baseline on, which is the only way a config gets created.

The SDK never writes a managed variable. Every agent reports what it says in code on one
`agent_control_config_hint` span, and turning that into a config -- or offering to refresh a stored
baseline the code has moved on from -- is a Logfire-side flow. This module is that span: its name,
its attributes, how much of a baseline a deployment lets off the process, and how one too large for a
span attribute gives up whole sections rather than being cut to length.

It is a contract with a consumer that queries it, so the span name and every attribute name here are
the same strings the other Agent Control SDKs emit. Two SDKs reporting one feature in two shapes is a
platform-side branch forever.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from ._config import AgentConfig, InstructionBlock, ParameterOverride, ToolDefinitionOverride
from ._schema import SCHEMA_SHA256, canonical_json

if TYPE_CHECKING:
    from logfire import Logfire
    from logfire._internal.config import LogfireConfig as _LogfireConfig
    from logfire.variables import ResolutionReason

BaselineSource: TypeAlias = Literal['code', 'observed']
"""Where a reported baseline came from, which an adapter has to say because it changes what it means.

- `'code'` is the agent *as written*: read off the agent object, its declared prompts, its declared
  settings, its tool definitions. It describes every request the agent will make.
- `'observed'` is one request, snapshotted because the framework offers nothing to read the agent
  from until it runs. It describes the request it came from and nothing else, so a prompt or a tool
  list assembled from the run's own input is a sample rather than a description -- and text that came
  from a request is one tenant's, one user's, one retrieved document's, reported into a project every
  member of it can read.

The distinction is not cosmetic: an adapter that can only observe should mark blocks it did not find
in code as dynamic rather than reporting their rendered text, and the editor has to be able to tell a
description of the code from a description of one request that happened first. It is also what
chooses the default [`BaselinePublication`][logfire.agent_control.BaselinePublication], because a
snapshot of one request is the case where reporting text is least likely to be what anyone wanted.
"""

BaselinePublication: TypeAlias = Literal['text', 'structure', 'off']
"""How much of a baseline leaves this process on the hint span.

- `'text'` reports the whole baseline: instruction text, tool descriptions, parameter descriptions.
  It is what makes the Logfire editor able to show the agent's own prompt as the thing a managed
  value is layered onto, and it is the right answer for a baseline read off the code.
- `'structure'` reports every seam and no text at all: instruction ids and their `dynamic` flags,
  tool names, toolsets, parameter names, the model, and the settings -- enough for the editor to
  offer an override for each of them, with none of the prose. This is the agent's baseline under that
  policy, not a redaction of a fuller one: the digest and the byte count describe what is reported, so
  two deployments running the same code under the same policy still agree.
- `'off'` reports no baseline at all. The span is still emitted -- the agent still registers, and
  `baseline_sha256` still says whether two reports describe the same code -- but
  `agent_control.baseline` is absent and `agent_control.baseline_reduction` is `'omitted'`, exactly as
  it is for a baseline too large to carry. One state on the span for "the document is not here", and
  no second word for a consumer to learn.

The default is `'structure'` when the baseline was observed and `'text'` when it was read off the
code, because that is where the two differ: code-side text is the author's, written knowing it is
editable from this Logfire project, while text snapshotted from a request is whoever's request it
happened to be.

`model` and `settings` survive `'structure'` -- a model id is a name and the canonical settings are
numbers, neither of which is anyone's content -- and the settings were already filtered to the
canonical keys by [`build_baseline`][logfire.agent_control.build_baseline], which is what keeps
`extra_headers` and signed bodies out of a baseline in the first place.
"""

BaselineReduction: TypeAlias = Literal['none', 'tool_definitions', 'omitted']
"""What a baseline gave up to fit `MAX_BASELINE_BYTES`, as `agent_control.baseline_reduction` reports it."""

CONFIG_HINT_SPAN_NAME = 'agent_control_config_hint'
"""The span an agent reports its code baseline on, and the name a Logfire-side query selects it by.

Static and separate from the message, so the message can be reworded without moving what the platform
indexes on. The attributes it carries are documented on `emit_config_hint`.
"""

CONFIG_HINT_MESSAGE = 'Agent Control reported the code baseline for this agent'
"""The hint span's message. The agent it is about is named by an attribute, so the message is the same
string for every agent in a project rather than one cardinality's worth of distinct messages."""

DEFAULT_FRAMEWORK = 'logfire'
"""Which Agent Control SDK a hint came from when nobody said.

`agent_control.framework` answers "whose baseline is this?", and the answer matters because the ids a
baseline addresses its instruction blocks by belong to whoever built it: `'agent:today'` means one
thing from the Pydantic AI capability and whatever an adapter decided from anywhere else. An adapter
names its framework -- `'pydantic-ai'`, `'mastra'`, `'openai-agents'` -- and uses the same string in
every language that adapts it, so the platform groups a TypeScript Mastra agent and a Python one
together.

The core is framework-neutral, so an application driving it directly is not using a framework at all
and naming one would be a guess. What a consumer needs from the attribute is still answerable: the
ids are this package's caller's own, and this package is the answer. It is not `'unknown'`, which
would conflate "there is no adapter" with "we did not find out". The TypeScript core answers
`'logfire-node'` by the same rule.
"""

MAX_BASELINE_BYTES = 1 << 20
"""How much serialized baseline a hint span will carry, in UTF-8 bytes.

Span attributes share a row budget in the low tens of megabytes, and the backend enforces it by
truncating a long string *in place* -- which for JSON means an attribute that still looks like a
string and no longer parses. So the budget is enforced here instead, an order of magnitude under the
row's, with room left for the rest of the span and for a consumer's own overhead. A baseline over it
gives up whole sections rather than being cut mid-string; see `serialize_baseline`.
"""


# Destinations an agent has already reported itself to in this process, per destination.
#
# Keyed on the Logfire *configuration* rather than on the `Logfire` object, because the configuration
# decides which project the config would live in and the wrapper does not: `logfire.with_settings(...)`
# returns a new `Logfire` over the same configuration, so a framework that builds its agent -- and a
# tagged instance -- per request would otherwise get a fresh key, and with it a report per request and
# a mapping that grows for the life of the process. Not collapsed to the variable name alone either: a
# process reconfigured onto a second project reports the agent to that one too, rather than letting
# the first project it touched stand in for both. The TypeScript core keys the same guard on its
# variables provider, which is the same fact where a language has one global instance.
#
# Keyed on the configuration's `id`, because `LogfireConfig` is a non-frozen dataclass and therefore
# unhashable, and identity is what is being asked about anyway. The configuration is kept in the value
# to make that safe: an `id` cannot be reused while the object it belongs to is still referenced.
_reported: dict[int, tuple[_LogfireConfig, set[str]]] = {}
_reported_lock = threading.Lock()


def reset_config_hint_guard() -> None:
    """Clear the once-per-process report guard. Intended for tests only."""
    with _reported_lock:
        _reported.clear()


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
    instructions = [
        InstructionBlock(id=entry.id, dynamic=entry.dynamic)
        for entry in baseline.instructions or []
        if isinstance(entry, InstructionBlock) and entry.id is not None
    ]
    tools = baseline.tool_definitions
    tool_definitions = None if tools is None else [_tool_seams(tool) for tool in tools]
    return baseline.model_copy(update={'instructions': instructions or None, 'tool_definitions': tool_definitions})


def _tool_seams(tool: ToolDefinitionOverride) -> ToolDefinitionOverride:
    """One tool's seams: the names an override addresses, and none of the prose."""
    return ToolDefinitionOverride(
        name=tool.name,
        new_name=tool.new_name,
        toolset=tool.toolset,
        parameters=None if tool.parameters is None else {name: ParameterOverride() for name in tool.parameters},
    )


def serialize_baseline(
    baseline: AgentConfig, publication: BaselinePublication
) -> tuple[str | None, BaselineReduction, int]:
    """Serialize a baseline to fit `MAX_BASELINE_BYTES`, dropping whole sections when it does not.

    Returns the JSON to put on the hint span (`None` when even the reduced baseline does not fit),
    which reduction was applied, and the baseline's size in UTF-8 bytes before any of it.

    Reduction drops `tool_definitions` first and then gives up, rather than trimming text to a budget.
    The contract already bounds a single instruction block, so a baseline this large is one with an
    unbounded *number* of things in it, and tool definitions are where that goes: every advertised
    tool, its description, and an entry per parameter. They are also the section a config needs least
    -- the editor can offer a tool override without one, while a baseline with no instructions has
    nothing to show at all. Either way the result is a whole, valid `AgentConfig` and the reduction is
    named on the span, so a consumer reads a baseline that is complete or knowingly partial, never one
    that parses into something the agent does not do.

    `'off'` lands in the same place a baseline too large to carry does, and says so the same way:
    there is one state on the span for "the document is not here", and a second word for it would
    only be a second thing for a consumer to learn.
    """
    serialized = dump_baseline(baseline)
    size = len(serialized.encode())
    if publication == 'off':
        return None, 'omitted', size
    if size <= MAX_BASELINE_BYTES:
        return serialized, 'none', size
    reduced = dump_baseline(baseline.model_copy(update={'tool_definitions': None}))
    if len(reduced.encode()) <= MAX_BASELINE_BYTES:
        return reduced, 'tool_definitions', size
    return None, 'omitted', size


def dump_baseline(baseline: AgentConfig) -> str:
    """The baseline as the JSON a hint carries, indented the way a variable's `example` is read."""
    return json.dumps(baseline.model_dump(exclude_none=True), indent=2)


def baseline_sha256(baseline: AgentConfig) -> str:
    """The digest that says whether two reports describe the same agent.

    Always over the *whole* reported baseline, never over the JSON the span ended up carrying. A
    baseline too large for a span attribute is reported with its tool definitions dropped, or with no
    baseline at all, and a digest taken after that would change when nothing about the agent had --
    and would leave every oversize report looking like every other one, which is the case that has
    nothing else to tell it apart by.

    "Reported" rather than "built" is the load-bearing word under `'structure'`: the stripped baseline
    *is* this deployment's baseline rather than a redaction of a fuller one, so two deployments running
    the same code under the same policy agree with each other. Under `'off'`, where nothing is carried
    at all, it is the built baseline, so a report still says whether the code has moved.

    Which makes this the digest of a document the span does not always carry: a consumer compares it
    with another hint's, and verifies it against `agent_control.baseline` only when
    `agent_control.baseline_reduction` is `'none'`.

    Over [`canonical_json`][logfire.agent_control.canonical_json], which is the same canonical form
    `SCHEMA_SHA256` uses, so an adapter computing a digest of its own agrees with this one and a
    baseline whose first instruction block has an accent in it does not digest differently in two
    languages.
    """
    return hashlib.sha256(canonical_json(baseline.model_dump(exclude_none=True))).hexdigest()


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
    config = instance.config
    attributes: dict[str, Any] = {
        'agent_control.service_name': config.service_name,
        'agent_control.environment': config.environment,
        'agent_control.service_version': config.service_version,
    }
    return {name: value for name, value in attributes.items() if value}


def emit_config_hint(
    *,
    logfire_instance: Logfire,
    variable_name: str,
    agent_name: str,
    baseline: AgentConfig,
    source: BaselineSource,
    framework: str,
    publication: BaselinePublication,
    resolution_reason: ResolutionReason,
) -> None:
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

    The baseline, both names and the three deployment attributes are exempt from Logfire's scrubbing
    (`logfire._internal.scrubbing.BaseScrubber.SAFE_KEYS`), which is what makes the digest something a
    consumer can verify. Scrubbing matches substrings, so an instruction block reading "Order tools are
    authoritative for status and refunds" would otherwise arrive as `[Scrubbed due to 'auth']`: the
    document a config is created from, rewritten after the digest and the byte count were taken over
    it, and an agent named `auth_router` reporting a `variable_name` that names no variable. A baseline
    is the author's own source text rather than runtime data, and what may enter it is already decided
    by the contract that builds it and by
    [`BaselinePublication`][logfire.agent_control.BaselinePublication], so a second substring-matching
    policy on top of that one corrupts it without adding protection.

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
    config = logfire_instance.config
    with _reported_lock:
        _, names = _reported.setdefault(id(config), (config, set()))
        if variable_name in names:
            return
        names.add(variable_name)

    reported = structure_only(baseline) if publication == 'structure' else baseline
    serialized, reduction, size = serialize_baseline(reported, publication)
    attributes: dict[str, Any] = {
        'agent_control.variable_name': variable_name,
        'agent_control.agent_name': agent_name,
        'agent_control.framework': framework,
        'agent_control.baseline_source': source,
        'agent_control.schema_sha256': SCHEMA_SHA256,
        'agent_control.baseline_sha256': baseline_sha256(reported),
        'agent_control.baseline_reduction': reduction,
        'agent_control.baseline_bytes': size,
        'agent_control.resolution_reason': resolution_reason,
        **deployment_attributes(logfire_instance),
    }
    if serialized is not None:
        attributes['agent_control.baseline'] = serialized
    # A decision that took no time, so the span opens and closes on the spot.
    with logfire_instance.span(CONFIG_HINT_MESSAGE, _span_name=CONFIG_HINT_SPAN_NAME, **attributes):
        pass
