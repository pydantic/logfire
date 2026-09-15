"""The span an agent reports its code baseline on.

The SDK never creates or updates a managed variable. Every agent reports its baseline on one
`agent_control_config_hint` span per process, carrying everything a config would be created from, and
creating one -- or offering to refresh a stored baseline the code has moved on from -- is a
Logfire-side flow. These tests are therefore the contract the platform side consumes: the span's name,
its attributes, when it is and is not emitted, how much of a baseline a deployment lets off the
process, and how a baseline too large for a span attribute degrades.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from typing import Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.agent_control import (
    SCHEMA_SHA256,
    AgentConfig,
    AgentControl,
    Block,
    InstructionBlock,
    Resolution,
    ToolDef,
    _control as control_module,  # pyright: ignore[reportPrivateUsage]
    _hint as hint_module,  # pyright: ignore[reportPrivateUsage]
    build_baseline,
    canonical_json,
)
from logfire.testing import CaptureLogfire
from logfire.variables import VariablesConfig
from logfire.variables.local import LocalVariableProvider

from .conftest import publish

SPAN_NAME = 'agent_control_config_hint'

BASELINE = build_baseline(instructions=[Block('You are a checkout assistant.', id='agent')])


def report(control: AgentControl, baseline: AgentConfig, **kwargs: Any) -> None:
    """Report `baseline` from inside the run's own resolution, which is where an adapter calls it."""
    with control.resolution() as resolution:
        control.report_baseline(baseline, resolution, **kwargs)


def hints(capfire: CaptureLogfire) -> list[dict[str, Any]]:
    """The attributes of each config-hint span this process exported, in order."""
    return [span['attributes'] for span in capfire.exporter.exported_spans_as_dict() if span['name'] == SPAN_NAME]


def baseline_of(attributes: dict[str, Any]) -> Any:
    """The `AgentConfig` a hint carries, parsed."""
    return json.loads(attributes['agent_control.baseline'])


def full_baseline() -> AgentConfig:
    """A baseline with something in every section, and a dynamic block the editor may only name."""
    return build_baseline(
        instructions=[
            Block('You are a checkout assistant.', id='agent'),
            Block('Today is Monday.', id='agent:today', dynamic=True),
        ],
        model='openai:gpt-5.6-sol',
        settings={'temperature': 0.3},
        tools=[
            ToolDef(
                name='get_weather',
                description='Get the current weather for a city.',
                parameters_json_schema={
                    'type': 'object',
                    'properties': {'city': {'description': 'City to look up.'}, 'units': {}},
                },
                toolset='weather',
            )
        ],
    )


def test_an_agent_reports_everything_a_config_would_be_created_from(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    control = AgentControl('checkout-assistant')
    with control.resolution() as resolution:
        control.report_baseline(full_baseline(), resolution)

    [attributes] = hints(capfire)
    # The identity half of the contract. `agent_name` is the name as written and `variable_name` is
    # what normalizing it produced, which is how a consumer tells two agents apart after they have
    # landed on one key.
    assert attributes['agent_control.variable_name'] == 'agent__checkout_assistant'
    assert attributes['agent_control.agent_name'] == 'checkout-assistant'
    assert attributes['agent_control.framework'] == 'logfire'
    assert attributes['agent_control.baseline_source'] == 'code'
    assert attributes['agent_control.schema_sha256'] == SCHEMA_SHA256
    assert attributes['agent_control.baseline_reduction'] == 'none'
    assert attributes['agent_control.baseline_bytes'] == len(attributes['agent_control.baseline'].encode())
    # Every agent reports, so the span's existence no longer says whether this one had a config. The
    # reason is what says it: `'code_default'` is a baseline waiting for a config to be created from
    # it, where `'resolved'` is one that may only be refreshing a stale example.
    assert attributes['agent_control.resolution_reason'] == 'code_default'
    # The message names no agent, so it stays one string across a project's agents. The span name is
    # separate from it, so the message can be reworded without moving what a query selects on.
    assert attributes['logfire.msg'] == 'Agent Control reported the code baseline for this agent'

    assert baseline_of(attributes) == {
        'instructions': [
            {'id': 'agent', 'instructions': 'You are a checkout assistant.', 'dynamic': False},
            # A dynamic block contributes its seam and never its text: what it rendered to is one
            # request's answer. The id and the flag are what the editor needs.
            {'id': 'agent:today', 'dynamic': True},
        ],
        'model': 'openai:gpt-5.6-sol',
        'settings': {'temperature': 0.3},
        'tool_definitions': [
            {
                'name': 'get_weather',
                'description': 'Get the current weather for a city.',
                'parameters': {'city': {'description': 'City to look up.'}, 'units': {}},
                'toolset': 'weather',
            }
        ],
    }
    assert 'Today is Monday' not in attributes['agent_control.baseline']


def test_reporting_writes_nothing_to_the_variable_api(
    project: LocalVariableProvider, capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The removed half of this class, asserted as the absence it now is.

    Creating the variable from the code baseline went through `create_variable`, and keeping that
    baseline current would have gone through `update_variable`. Both are refused rather than merely
    observed, so what this asserts is that no write was *attempted* -- a project that happens to look
    unchanged is not the same claim.
    """
    for method in ('create_variable', 'update_variable', 'delete_variable'):
        monkeypatch.setattr(project, method, _refuse(method))

    report(AgentControl('checkout'), BASELINE)

    assert project.get_variable_config('agent__checkout') is None
    assert len(hints(capfire)) == 1


def test_the_hint_says_which_deployment_reported_the_baseline(capfire: CaptureLogfire) -> None:
    """A variable is derived from the agent's name alone, so the span has to say whose code this is.

    Two services that each define a `checkout` land on one `agent__checkout`, and so do the same
    service's dev and prod deployments, since a variable is one value per project and the dev/prod
    split is its labels. The identity comes off the Logfire instance the hint is emitted on, so it is
    whatever the deployment already told `logfire.configure()` rather than something to configure
    twice.
    """
    instance = _local_project(capfire, service_name='checkout', service_version='1a2b3c4', environment='prod')
    report(AgentControl('checkout', logfire_instance=instance), BASELINE)

    [attributes] = hints(capfire)
    assert attributes['agent_control.service_name'] == 'checkout'
    assert attributes['agent_control.service_version'] == '1a2b3c4'
    assert attributes['agent_control.environment'] == 'prod'


def test_the_hint_is_reported_as_written_with_scrubbing_at_its_default(capfire: CaptureLogfire) -> None:
    """Nothing on this span is rewritten by Logfire's scrubbing, which is on unless a project turns it off.

    Scrubbing matches substrings, and `auth`, `session`, `token`, `secret` and `credential` are
    ordinary words in a prompt, a tool description, an agent's name and a service's name. Every string
    here would match one: the instruction says "authoritative", the tool description says
    "authorization", the agent is an `auth_router` and the service is a `checkout-session-api`. The
    baseline is the document a config is created from, so a redaction inside it is a corrupted
    document rather than a hidden secret -- and it would be a corrupted document that no longer
    matches the digest or the byte count, both of which are taken over the baseline before it is
    exported. A redacted `variable_name` is worse still: the hint names no variable, so the agent is
    invisible with nothing raised anywhere.

    The exemption lives in `BaseScrubber.SAFE_KEYS` in this package. This test is what holds it there.
    """
    # The deployment identity matches the patterns the same way an ordinary one does: a service that
    # serves checkout sessions, a preview environment named after the branch it was built from, and a
    # version string carrying that branch name.
    instance = _local_project(
        capfire,
        service_name='checkout-session-api',
        service_version='1.4.0+authz.2',
        environment='pr-auth-refresh',
    )
    instructions = 'Order tools are authoritative for status and refunds.'
    description = 'Refund an order the customer has authorization for.'
    baseline = build_baseline(
        instructions=[Block(instructions, id='agent')],
        tools=[ToolDef(name='refund_order', description=description, toolset='orders')],
    )
    report(AgentControl('auth_router', logfire_instance=instance), baseline)

    [attributes] = hints(capfire)
    carried = baseline_of(attributes)
    assert carried['instructions'] == [{'id': 'agent', 'instructions': instructions, 'dynamic': False}]
    assert carried['tool_definitions'] == [{'name': 'refund_order', 'description': description, 'toolset': 'orders'}]
    assert attributes['agent_control.variable_name'] == 'agent__auth_router'
    assert attributes['agent_control.agent_name'] == 'auth_router'
    assert attributes['agent_control.service_name'] == 'checkout-session-api'
    assert attributes['agent_control.service_version'] == '1.4.0+authz.2'
    assert attributes['agent_control.environment'] == 'pr-auth-refresh'
    # The two promises the reduction being `'none'` makes to a consumer, checked against the document
    # the span actually carries rather than against the one this process built.
    assert attributes['agent_control.baseline_reduction'] == 'none'
    assert attributes['agent_control.baseline_sha256'] == hashlib.sha256(canonical_json(carried)).hexdigest()
    assert attributes['agent_control.baseline_bytes'] == len(attributes['agent_control.baseline'].encode())
    # Scrubbing records what it rewrote, so its absence covers every attribute of the span rather
    # than the ones this test happens to name -- including the run's own
    # `logfire.variables.agent__auth_router`, whose key is built from the variable's name and is
    # covered by `SAFE_KEY_PREFIXES` rather than by a listed key.
    assert 'logfire.scrubbed' not in attributes


def test_identity_the_sdk_does_not_know_is_left_off(project: LocalVariableProvider, capfire: CaptureLogfire) -> None:
    # Absent rather than `''`: absent is a state a consumer can act on -- group these hints by
    # deployment, or say it cannot -- where an empty string is a value it has to learn to disbelieve.
    # `service_version` is not asserted here: Logfire fills it in from the commit of the checkout the
    # process runs in, so what it holds depends on where the tests run rather than on this code.
    report(AgentControl('checkout'), BASELINE)

    [attributes] = hints(capfire)
    assert 'agent_control.service_name' not in attributes
    assert 'agent_control.environment' not in attributes


def test_an_adapter_says_which_framework_the_baseline_came_from(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # The ids a baseline addresses its blocks by belong to whoever built it, so a consumer has to
    # know whose baseline it is reading. An adapter passes its framework's own slug; the default
    # names this core, driven directly by an agent someone wrote the hook for themselves.
    report(AgentControl('adapted', framework='openai-agents'), BASELINE)
    report(AgentControl('bare'), BASELINE)

    assert [attributes['agent_control.framework'] for attributes in hints(capfire)] == ['openai-agents', 'logfire']


def test_the_baseline_digest_changes_only_when_the_code_does(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # The guard reports one baseline per process per variable, so a code change that happens while
    # the process runs is never re-reported. The digest is what makes that detectable at all: a
    # consumer holding an earlier hint can tell "the same baseline again" from "this agent has moved".
    for name, instructions in (('one', 'CODE one.'), ('two', 'CODE two.'), ('one_again', 'CODE one.')):
        report(AgentControl(name), build_baseline(instructions=[Block(instructions, id='agent')]))

    one, two, again = (attributes['agent_control.baseline_sha256'] for attributes in hints(capfire))
    assert one != two
    assert one == again


def test_the_baseline_digest_uses_the_contracts_canonical_json(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """One definition of canonical, and the reason it is exported rather than restated.

    `SCHEMA_SHA256` is taken over sorted keys, `(',', ':')` separators, and `ensure_ascii=False`, and
    a baseline digest has to be taken over the same three or a TypeScript core computing one would
    not agree with this one. The probe is non-ASCII on purpose: `ensure_ascii` is the flag an ASCII
    document cannot tell apart, and it is the one a prompt in any other language would expose first.
    """
    baseline = build_baseline(instructions=[Block('Grüße, ¿cómo estás?', id='agent')])
    report(AgentControl('accented'), baseline)

    [attributes] = hints(capfire)
    expected = hashlib.sha256(canonical_json(baseline.model_dump(exclude_none=True))).hexdigest()
    assert attributes['agent_control.baseline_sha256'] == expected


def test_a_configured_agent_still_reports_its_code_baseline(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """A config reaching the run does not stop the agent describing itself.

    The baseline the Logfire editor diffs against is a copy of the code, and code moves: an agent that
    reported only while unconfigured would go quiet the moment somebody configured it, and its stored
    baseline would describe the deployment it was created from forever. So the hint says what the code
    says now, whatever is published, and `resolution_reason` says which of the two jobs it is for.
    """
    publish(project, 'agent__checkout', {'instructions': 'MANAGED: be brief.'})
    control = AgentControl('checkout', label='production')
    with control.resolution() as resolution:
        assert resolution.config is not None
        control.report_baseline(BASELINE, resolution)

    [attributes] = hints(capfire)
    assert attributes['agent_control.resolution_reason'] == 'resolved'
    # What it carries is still the code and never the managed value -- that is what makes a diff a diff.
    assert baseline_of(attributes)['instructions'] == [
        {'id': 'agent', 'instructions': 'You are a checkout assistant.', 'dynamic': False}
    ]


def test_the_reported_reason_is_the_runs_and_not_a_second_resolve(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """The run hands its resolution in, so the span cannot describe a version the agent never ran on.

    Resolving again inside the report would read the variable a second time, and a value published --
    or a rollout landing differently -- between the two would put a reason on the span that no request
    of this run was made under. The resolution the run is actually using is the one that is reported,
    even where reading the project again would answer differently.
    """
    carried = Resolution(
        config=None, label='canary', version=7, reason='context_override', variable_name='agent__checkout'
    )
    AgentControl('checkout').report_baseline(BASELINE, carried)

    [attributes] = hints(capfire)
    assert attributes['agent_control.resolution_reason'] == 'context_override'


def test_an_agent_reports_once_per_process(project: LocalVariableProvider, capfire: CaptureLogfire) -> None:
    # The guard is what bounds the cost of reporting unconditionally, and it is on the destination
    # rather than on the object: a second `AgentControl` for one agent -- a process that rebuilds its
    # agent per request, a test suite -- is one configuration stated twice.
    report(AgentControl('checkout'), BASELINE)
    report(AgentControl('checkout'), full_baseline())

    assert len(hints(capfire)) == 1


def test_a_per_request_logfire_instance_is_still_one_destination(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # `with_settings` returns a new `Logfire` over the same configuration, so a framework that tags
    # per request and rebuilds its agent with it would report per request -- and hold every wrapper
    # for the life of the process -- if the guard were keyed on the wrapper.
    for index in range(3):
        instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(tags=[f'request-{index}'])
        report(AgentControl('checkout', logfire_instance=instance), BASELINE)

    assert len(hints(capfire)) == 1


def test_each_logfire_project_is_reported_to(capfire: CaptureLogfire) -> None:
    # A process can serve several Logfire projects, and a config in the first is not a config in the
    # second, so the guard is keyed by destination as well as by variable name. Each hint also has to
    # be emitted on its own project's instance rather than on whichever one happens to be the default.
    for _ in range(2):
        instance = _local_project(capfire)
        report(AgentControl('two_projects', logfire_instance=instance), BASELINE)
        # A second report to the same instance is still guarded.
        report(AgentControl('two_projects', logfire_instance=instance), BASELINE)

    assert [attributes['agent_control.variable_name'] for attributes in hints(capfire)] == [
        'agent__two_projects',
        'agent__two_projects',
    ]


def test_an_agent_with_no_variables_provider_is_still_reported(capfire: CaptureLogfire) -> None:
    # Registration used to need the variable-management API, which a process holding only a
    # span-write token does not have. A hint travels the span pipeline, so that process -- here, one
    # configured with no variables provider at all -- registers too.
    report(AgentControl('no_provider'), BASELINE)

    assert [attributes['agent_control.variable_name'] for attributes in hints(capfire)] == ['agent__no_provider']


def test_the_hint_survives_a_raised_min_level(capfire: CaptureLogfire) -> None:
    """A hint is a span and not a log record, so a logging threshold cannot withhold it.

    `min_level` drops a log below it before it is ever exported, and a span with no level of its own
    is not subject to it. The platform side of Agent Control depends on this signal arriving, which is
    not something a project's logging configuration should get a vote on.
    """
    instance = _local_project(capfire, min_level='warn')
    report(AgentControl('quiet_project', logfire_instance=instance), BASELINE)

    assert [attributes['agent_control.variable_name'] for attributes in hints(capfire)] == ['agent__quiet_project']


def test_an_observed_baseline_reports_its_seams_and_none_of_its_text(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """The default for a snapshot of one request, which is the case nobody asked to publish text for.

    An adapter whose framework offers nothing to read the agent from until it runs is describing the
    request it happened to see: that prompt is one tenant's, one user's, one retrieved document's. So
    an observed baseline reports every seam -- every id, every tool and parameter name -- and no prose
    at all, and the editor keeps its whole override surface without the project reading a request.
    """
    report(AgentControl('observed'), full_baseline(), source='observed')

    [attributes] = hints(capfire)
    assert attributes['agent_control.baseline_source'] == 'observed'
    assert baseline_of(attributes) == {
        'instructions': [{'id': 'agent', 'dynamic': False}, {'id': 'agent:today', 'dynamic': True}],
        'model': 'openai:gpt-5.6-sol',
        'settings': {'temperature': 0.3},
        # Names and toolsets survive, so every tool can still be addressed; descriptions do not.
        'tool_definitions': [{'name': 'get_weather', 'parameters': {'city': {}, 'units': {}}, 'toolset': 'weather'}],
    }
    assert 'checkout assistant' not in attributes['agent_control.baseline']
    assert 'City to look up' not in attributes['agent_control.baseline']


def test_a_deployment_can_pin_the_publication_mode_either_way(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # The source chooses a default and the deployment overrules it in both directions: a team that
    # cannot let prompt text into a project-readable artifact pins `'structure'` for a code baseline,
    # and one that wants the editor to open on real text accepts an observed one with `'text'`.
    report(AgentControl('pinned_structure', report_baseline='structure'), full_baseline())
    report(AgentControl('pinned_text', report_baseline='text'), full_baseline(), source='observed')

    structure, text = hints(capfire)
    assert 'checkout assistant' not in structure['agent_control.baseline']
    assert 'You are a checkout assistant.' in text['agent_control.baseline']
    # The stripped baseline *is* this deployment's baseline, so the digest and the size describe what
    # was reported. Two deployments running this code under this policy agree with each other, and
    # neither has to reconstruct what a fuller report would have said.
    assert structure['agent_control.baseline_bytes'] == len(structure['agent_control.baseline'].encode())
    assert structure['agent_control.baseline_sha256'] != text['agent_control.baseline_sha256']


def test_publication_turned_off_still_registers_the_agent(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """`'off'` withholds the document, not the agent.

    It lands in the state a baseline too large to carry lands in, and says so the same way: there is
    one `baseline_reduction` value for "the document is not here", and a second word for it would only
    be a second thing for a consumer to learn. The agent still appears on the Agent Control page, and
    `baseline_sha256` still says whether two reports describe the same code -- over the baseline as
    built, since nothing was stripped from it, only withheld.
    """
    report(AgentControl('silent', report_baseline='off'), full_baseline())

    [attributes] = hints(capfire)
    assert attributes['agent_control.variable_name'] == 'agent__silent'
    assert attributes['agent_control.baseline_reduction'] == 'omitted'
    assert 'agent_control.baseline' not in attributes
    assert (
        attributes['agent_control.baseline_sha256']
        == hashlib.sha256(canonical_json(full_baseline().model_dump(exclude_none=True))).hexdigest()
    )


def test_structure_drops_an_entry_it_would_leave_nothing_of(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # A bare string, or an entry an adapter built with no id, carries text and nothing else. Under
    # `'structure'` there is no text to report and no seam to report instead, so what would be left is
    # an entry naming nothing -- which an editor can neither show nor offer an override for.
    baseline = AgentConfig(
        instructions=['a bare added block', InstructionBlock(instructions='no id either'), InstructionBlock(id='agent')]
    )
    report(AgentControl('addressless', report_baseline='structure'), baseline)

    [attributes] = hints(capfire)
    assert baseline_of(attributes) == {'instructions': [{'id': 'agent'}]}


def test_structure_with_nothing_addressable_left_reports_the_empty_sections_away(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # Emptied sections are left out rather than sent as `[]`: an absent section means "leave this to
    # code" everywhere else in the contract, and a baseline is read with the same eyes.
    report(
        AgentControl('nothing_left', report_baseline='structure'),
        build_baseline(instructions=[Block('text with no id')], model='openai:gpt-5.6-sol'),
    )

    [attributes] = hints(capfire)
    assert baseline_of(attributes) == {'model': 'openai:gpt-5.6-sol'}


def test_an_oversized_baseline_drops_its_tool_definitions(
    project: LocalVariableProvider, capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A baseline over the budget gives up whole sections rather than being cut to length.

    The backend enforces its own attribute budget by truncating a long string in place, which for
    JSON yields an attribute that still looks like a string and no longer parses. So the reduction
    happens here, is named on the span, and leaves a whole valid `AgentConfig` behind.
    """
    # A budget between this agent's full baseline and the same baseline without its tool definitions,
    # so the first rung of the ladder is the one taken.
    monkeypatch.setattr(hint_module, 'MAX_BASELINE_BYTES', 300)
    report(AgentControl('oversized'), full_baseline())

    [attributes] = hints(capfire)
    assert attributes['agent_control.baseline_reduction'] == 'tool_definitions'
    # Still a parseable, whole config, with the section that carries the unbounded part left out.
    assert baseline_of(attributes) == {
        'instructions': [
            {'id': 'agent', 'instructions': 'You are a checkout assistant.', 'dynamic': False},
            {'id': 'agent:today', 'dynamic': True},
        ],
        'model': 'openai:gpt-5.6-sol',
        'settings': {'temperature': 0.3},
    }
    # The size reported is the full baseline's, so a consumer sees how far over the budget it was
    # rather than how big the part that survived is.
    assert attributes['agent_control.baseline_bytes'] > len(attributes['agent_control.baseline'].encode())


def test_a_baseline_too_large_even_reduced_is_omitted_and_says_so(
    project: LocalVariableProvider, capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing is guessed at and nothing is cut: the hint still registers the agent, and the reduction
    # says why no baseline is on it.
    monkeypatch.setattr(hint_module, 'MAX_BASELINE_BYTES', 10)
    report(AgentControl('omitted'), full_baseline())

    [attributes] = hints(capfire)
    assert attributes['agent_control.baseline_reduction'] == 'omitted'
    assert 'agent_control.baseline' not in attributes
    assert attributes['agent_control.variable_name'] == 'agent__omitted'
    assert attributes['agent_control.baseline_bytes'] > 10


def test_a_reduced_baseline_still_digests_the_whole_one(
    project: LocalVariableProvider, capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reduction changes what the span carries, and must not change what the digest says.

    The same code reported twice, once under a budget that leaves no room for a baseline at all. A
    digest taken after the reduction would make those two look like different agents -- and would
    leave every omitted report looking like every other one, which is the case with nothing else on
    the span to tell it apart by.
    """
    report(AgentControl('whole'), full_baseline())
    with monkeypatch.context() as clamped:
        clamped.setattr(hint_module, 'MAX_BASELINE_BYTES', 10)
        report(AgentControl('clamped'), full_baseline())

    whole, clamped_attributes = hints(capfire)
    assert whole['agent_control.baseline_reduction'] == 'none'
    assert clamped_attributes['agent_control.baseline_reduction'] == 'omitted'
    assert clamped_attributes['agent_control.baseline_sha256'] == whole['agent_control.baseline_sha256']


def test_the_budget_stays_an_order_of_magnitude_under_the_backends() -> None:
    # A guard on the constant itself. The whole point of enforcing a budget here is to stay well under
    # the row budget the backend truncates against, so a change to it is a decision to make
    # deliberately rather than a number to drift.
    assert hint_module.MAX_BASELINE_BYTES == 1024 * 1024


def test_a_report_that_fails_is_said_once_and_never_raised(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing property: the caller is serving a request.

    A baseline is documentation that no request depends on, so nothing about describing the agent may
    reach the agent as a crash -- and the report is guarded before the work, so one failure is not
    retried on every later request either.
    """
    monkeypatch.setattr(control_module, 'emit_config_hint', _refuse('emit_config_hint'))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        report(AgentControl('broken'), BASELINE)
        # The guard was marked before the work, so the failure is not retried on the next request.
        report(AgentControl('broken'), BASELINE)

    assert [str(warning.message) for warning in caught] == [
        "Failed to report the code baseline for Logfire managed variable 'agent__broken': "
        'the variables token is read-only'
    ]


def _local_project(capfire: CaptureLogfire, **kwargs: Any) -> logfire.Logfire:
    """A Logfire instance of its own, exporting into this test's collector."""
    return logfire.configure(
        local=True,
        send_to_logfire=False,
        console=False,
        variables=logfire.LocalVariablesOptions(config=VariablesConfig(variables={})),
        additional_span_processors=[SimpleSpanProcessor(capfire.exporter)],
        **kwargs,
    )


def _refuse(name: str) -> Any:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise PermissionError('the variables token is read-only')

    refuse.__name__ = name
    return refuse
