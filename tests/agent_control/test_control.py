"""Reading the published config, and publishing the baseline the editor diffs it against."""

from __future__ import annotations

import json
import warnings
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest

import logfire
from logfire.agent_control import (
    AGENT_CONFIG_JSON_SCHEMA,
    AgentControl,
    Block,
    Resolution,
    build_baseline,
    current_resolution,
    use_resolution,
)
from logfire.testing import CaptureLogfire
from logfire.variables import LabeledValue, Rollout, Variable, VariableAlreadyExistsError, VariableConfig
from logfire.variables.local import LocalVariableProvider

from .conftest import publish

BASELINE = build_baseline(instructions=[Block('You are a checkout assistant.', id='agent')])
BASELINE_EXAMPLE = json.dumps(BASELINE.model_dump(exclude_none=True), indent=2)


@contextmanager
def collected_warnings() -> Generator[list[warnings.WarningMessage]]:
    """Collect warnings from this thread and the publish thread, without the suite's error filter."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        yield caught


def published_baseline(provider: LocalVariableProvider, name: str) -> str | None:
    config = provider.get_variable_config(name)
    return None if config is None else config.example


def test_the_variable_is_named_after_the_agent() -> None:
    control = AgentControl('checkout-assistant', label='production')
    # The display name is kept as given -- it is what a person recognizes the agent by -- and the key
    # is that name normalized, so it can be made to read better without moving the config.
    assert (control.name, control.variable_name, control.label) == (
        'checkout-assistant',
        'agent__checkout_assistant',
        'production',
    )
    assert control.on_unmatched == 'warn'
    assert repr(control) == "AgentControl(name='checkout-assistant', label='production')"


def test_names_that_differ_only_in_punctuation_and_case_share_one_config() -> None:
    # Lossy on purpose: it is the Logfire UI's own rule, which is what makes a Pydantic AI agent and
    # a Mastra agent that a person calls by the same name land on the config the UI shows for them.
    keys = {
        AgentControl(name).variable_name for name in ('Checkout Assistant', 'checkout-assistant', 'CHECKOUT_ASSISTANT')
    }
    assert keys == {'agent__checkout_assistant'}


def test_the_spec_vectors_are_what_this_core_does(agent_name_vectors: list[dict[str, Any]]) -> None:
    # The same file the TypeScript core runs against: one rule, or a Logfire project holds two
    # configs for one agent and shows one of them.
    for vector in agent_name_vectors:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            try:
                control = AgentControl(vector['input'])
            except ValueError:
                assert vector.get('error') == 'empty', vector['name']
            else:
                assert (control.name, control.variable_name) == (vector['display_name'], vector['variable_name']), (
                    vector['name']
                )
        warned = ['prefix-added-automatically'] if caught else []
        assert warned == ([vector['warning']] if vector.get('warning') else []), vector['name']


def test_the_prefix_is_added_for_you() -> None:
    with pytest.warns(UserWarning, match="prefix is added automatically; pass the bare agent name rather than 'agent"):
        control = AgentControl('agent__checkout')
    assert control.variable_name == 'agent__checkout'


def test_nothing_published_runs_the_agent_as_written(project: LocalVariableProvider) -> None:
    assert project.get_variable_config('agent__checkout') is None
    assert AgentControl('checkout').resolve() is None


def test_no_provider_configured_runs_the_agent_as_written() -> None:
    assert AgentControl('checkout').resolve() is None


def test_a_published_value_is_what_the_agent_runs(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout',
        {
            'instructions': [{'id': 'agent', 'instructions': 'You are a refund specialist.'}],
            'model': 'anthropic:claude-fable-5-1',
            'settings': {'temperature': 0.4},
        },
    )
    config = AgentControl('checkout', label='production').resolve()
    assert config is not None
    assert config.model == 'anthropic:claude-fable-5-1'
    assert config.settings is not None and config.settings.temperature == 0.4


def test_the_rollout_chooses_the_label_when_the_agent_names_none(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'}, label='canary')
    config = AgentControl('checkout').resolve()
    assert config is not None and config.model == 'openai:gpt-5.6-sol'


def test_a_published_value_degrades_one_entry_at_a_time(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol', 'settings': {'temperature': 'hot'}})
    with pytest.warns(UserWarning, match="setting 'temperature' has invalid value 'hot'"):
        config = AgentControl('checkout', label='production').resolve()
    assert config is not None and config.model == 'openai:gpt-5.6-sol'


def test_a_stored_value_this_release_cannot_parse_runs_the_agent_as_written(project: LocalVariableProvider) -> None:
    # Not lenient-able: the whole value is not an object, so there is no entry to keep.
    publish(project, 'agent__checkout', ['not a config'])
    with collected_warnings() as caught:
        assert AgentControl('checkout', label='production').resolve() is None
    assert any('agent__checkout' in str(warning.message) for warning in caught)


def test_a_provider_that_cannot_be_reached_says_so_once(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError('logfire-api.pydantic.dev is unreachable')

    monkeypatch.setattr(project, 'get_serialized_value', unreachable)
    control = AgentControl('checkout')
    with collected_warnings() as caught:
        assert control.resolve() is None
        # The config is read on every run, so the signal has to survive its own repetition.
        assert control.resolve() is None
    ours = [w for w in caught if 'Failed to read the Logfire managed config' in str(w.message)]
    assert len(ours) == 1
    assert 'unreachable' in str(ours[0].message)


def test_reading_the_config_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('the SDK itself fell over')

    monkeypatch.setattr(Variable, 'get', boom)
    with pytest.warns(UserWarning, match='the SDK itself fell over'):
        assert AgentControl('checkout').resolve() is None


def test_a_run_inside_a_resolution_carries_the_version_that_produced_it(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'}, label='canary')
    with AgentControl('checkout', label='canary').resolution() as resolution:
        assert resolution.config is not None and resolution.config.model == 'openai:gpt-5.6-sol'
        assert (resolution.label, resolution.version, resolution.reason) == ('canary', 1, 'resolved')
        logfire.info('the run')
    # Every span emitted inside the block says which published version produced it, which is what
    # lets a regression be traced back to the value that caused it.
    [run] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'the run']
    assert run['attributes']['logfire.variables.agent__checkout'] == 'canary'
    assert run['attributes']['logfire.variables.agent__checkout.version'] == '1'


def test_a_later_block_can_report_the_version_the_run_resolved(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    # An adapter whose framework resolves in one place and calls the model in another carries the
    # resolution through the framework's own state and reports it again around each later block.
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'}, label='canary')
    with AgentControl('checkout', label='canary').resolution() as resolution:
        pass
    with resolution.reported():
        logfire.info('a later graph node')
    [node] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'a later graph node']
    assert node['attributes']['logfire.variables.agent__checkout'] == 'canary'
    assert node['attributes']['logfire.variables.agent__checkout.version'] == '1'


def test_reporting_a_resolution_that_never_happened_does_nothing(
    capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('the SDK itself fell over')

    monkeypatch.setattr(Variable, 'get', boom)
    with pytest.warns(UserWarning, match='the SDK itself fell over'):
        with AgentControl('checkout').resolution() as resolution:
            pass
    with resolution.reported():
        logfire.info('a later graph node')
    [node] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'a later graph node']
    assert not [key for key in node['attributes'] if key.startswith('logfire.variables.')]


def test_a_resolution_with_nothing_published_says_why(project: LocalVariableProvider) -> None:
    with AgentControl('checkout').resolution() as resolution:
        assert resolution == Resolution(
            config=None, label=None, version=None, reason='code_default', variable_name='agent__checkout'
        )


def test_a_resolution_that_could_not_be_read_at_all_is_still_a_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('the SDK itself fell over')

    monkeypatch.setattr(Variable, 'get', boom)
    with pytest.warns(UserWarning, match='the SDK itself fell over'):
        with AgentControl('checkout').resolution() as resolution:
            assert resolution == Resolution(
                config=None, label=None, version=None, reason='other_error', variable_name='agent__checkout'
            )


def test_an_adapter_reports_what_it_cannot_apply_through_the_configured_policy() -> None:
    message = 'Managed agent config selects model X, which this framework cannot switch per request.'
    with pytest.warns(UserWarning, match='cannot switch per request'):
        AgentControl('checkout').report_unmatched(message)
    AgentControl('checkout', on_unmatched='ignore').report_unmatched(message)
    with pytest.raises(ValueError, match='cannot switch per request'):
        AgentControl('checkout', on_unmatched='error').report_unmatched(message)


def test_publishing_creates_the_variable_with_the_stored_schema(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    assert config.json_schema == AGENT_CONFIG_JSON_SCHEMA
    assert config.example == BASELINE_EXAMPLE
    # Creating a variable writes a teammate-visible object into the project, so the project is where
    # it is reported -- a `warnings.warn` on a daemon thread is invisible.
    assert any('Created Logfire managed variable' in span.name for span in capfire.exporter.exported_spans)


def test_publishing_updates_only_the_example_of_a_variable_that_exists(project: LocalVariableProvider) -> None:
    existing = publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'})
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    assert config.example == BASELINE_EXAMPLE
    # The published value, its labels, and its rollout survive a baseline write.
    assert config.labels == existing.labels
    assert config.rollout == existing.rollout


def test_publishing_writes_nothing_when_the_baseline_already_matches(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.create_variable(
        VariableConfig(
            name='agent__checkout',
            labels={'production': LabeledValue(version=1, serialized_value='{}')},
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
            example=BASELINE_EXAMPLE,
        )
    )
    monkeypatch.setattr(project, 'update_variable', _refuse('update_variable'))
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    assert published_baseline(project, 'agent__checkout') == BASELINE_EXAMPLE


def test_publishing_happens_once_per_process_per_variable(project: LocalVariableProvider) -> None:
    control = AgentControl('checkout')
    thread = control.publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    # A second agent object for the same agent -- a process that rebuilds its agent per request --
    # is one configuration stated twice, and the guard is on the destination rather than the object.
    assert AgentControl('checkout').publish_baseline(build_baseline()) is None
    assert published_baseline(project, 'agent__checkout') == BASELINE_EXAMPLE


def test_publishing_can_be_turned_off_for_a_read_only_token(project: LocalVariableProvider) -> None:
    assert AgentControl('checkout', publish_baseline=False).publish_baseline(BASELINE) is None
    assert project.get_variable_config('agent__checkout') is None


def test_publishing_with_no_provider_configured_is_not_a_failure() -> None:
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    with collected_warnings() as caught:
        thread.join()
    assert caught == []


def test_a_variable_created_by_someone_else_first_is_not_a_failure(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def already_exists(_config: VariableConfig) -> VariableConfig:
        raise VariableAlreadyExistsError("Variable 'agent__checkout' already exists")

    monkeypatch.setattr(project, 'create_variable', already_exists)
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    with collected_warnings() as caught:
        thread.join()
    assert caught == []


def test_a_failed_publish_is_reported_and_never_raised(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'})
    monkeypatch.setattr(project, 'update_variable', _refuse('update_variable'))
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    with collected_warnings() as caught:
        thread.join()
    assert [str(warning.message) for warning in caught] == [
        "Failed to publish the code baseline for Logfire managed variable 'agent__checkout': "
        'the variables token is read-only'
    ]


def test_an_explicit_logfire_instance_is_the_one_written_to(project: LocalVariableProvider) -> None:
    instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(tags=['agent-control'])
    thread = AgentControl('checkout', logfire_instance=instance).publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    assert published_baseline(project, 'agent__checkout') == BASELINE_EXAMPLE


def test_two_hooks_in_one_run_read_the_one_resolution_the_run_made(project: LocalVariableProvider) -> None:
    # The reason this exists: a framework that hands an adapter an instructions callable and a model
    # wrapper, with nothing bracketing both. Resolving in each of them can send prompt A with model B
    # when a publish or a rollout lands between the two.
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'}, label='canary')
    control = AgentControl('checkout', label='canary')
    assert control.current_resolution() is None
    with control.resolution() as resolution:
        assert control.current_resolution() is resolution
        assert current_resolution('agent__checkout') is resolution
    assert control.current_resolution() is None

    # ... and the same resolution, carried in the framework's own per-run state, re-entered later.
    with use_resolution(resolution):
        assert control.current_resolution() is resolution


def test_a_scope_carries_the_version_onto_the_spans_inside_it(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'}, label='canary')
    with AgentControl('checkout', label='canary').resolution() as resolution:
        pass
    with use_resolution(resolution):
        logfire.info('a later graph node')
    [node] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'a later graph node']
    assert node['attributes']['logfire.variables.agent__checkout'] == 'canary'


def test_two_agents_nested_each_keep_answering_about_themselves(project: LocalVariableProvider) -> None:
    # A handoff, a subagent, a tool that runs another managed agent: the inner scope must not make
    # the outer agent's control answer with the inner agent's config.
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'})
    publish(project, 'agent__billing', {'model': 'anthropic:claude-fable-5-1'})
    checkout = AgentControl('checkout', label='production')
    billing = AgentControl('billing', label='production')
    with checkout.resolution() as outer:
        with billing.resolution() as inner:
            assert checkout.current_resolution() is outer
            assert billing.current_resolution() is inner
        assert billing.current_resolution() is None
        assert checkout.current_resolution() is outer


def test_a_run_that_could_not_read_its_config_still_answers_its_later_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('the SDK itself fell over')

    monkeypatch.setattr(Variable, 'get', boom)
    control = AgentControl('checkout')
    with pytest.warns(UserWarning, match='the SDK itself fell over'):
        with control.resolution() as resolution:
            # "Resolved to nothing" is an answer; "you are not in a run" is not the same answer.
            assert control.current_resolution() is resolution
            assert resolution.config is None


def test_publishing_says_whether_the_baseline_is_the_code_or_one_request(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    thread = AgentControl('checkout').publish_baseline(BASELINE, source='observed')
    assert thread is not None
    thread.join()
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    # The distinction reaches the person reading the variable, because it changes what the example
    # means: a description of the code, or a snapshot of the one request that happened first.
    assert config.description is not None and 'snapshotted from one request' in config.description
    [created] = [span for span in capfire.exporter.exported_spans if 'Created Logfire managed' in span.name]
    assert created.attributes is not None and created.attributes['baseline_source'] == 'observed'


def test_a_code_baseline_says_so_instead(project: LocalVariableProvider) -> None:
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    assert config.description is not None and 'the agent as written' in config.description


def test_the_example_written_back_is_the_one_read_immediately_before_writing(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The narrowest the client side can make the lost-update window: everything the UI saved up to
    # the last read survives, and only an edit landing inside the remaining round trip is lost. With
    # one read, the value the UI published here would have been restored to what it was before.
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'})
    real_get = project.get_variable_config
    reads = 0

    def get_variable_config(name: str) -> Any:
        nonlocal reads
        reads += 1
        if reads == 1:
            # Between the read that found the variable and the write, someone publishes in the UI.
            existing = real_get(name)
            assert existing is not None
            project.update_variable(
                name,
                existing.model_copy(
                    update={
                        'labels': {
                            'production': LabeledValue(
                                version=2, serialized_value=json.dumps({'model': 'anthropic:claude-fable-5-1'})
                            )
                        }
                    }
                ),
            )
        return real_get(name)

    monkeypatch.setattr(project, 'get_variable_config', get_variable_config)
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    thread.join()
    monkeypatch.undo()
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    assert config.example == BASELINE_EXAMPLE
    value = config.labels['production']
    assert isinstance(value, LabeledValue)
    assert json.loads(value.serialized_value)['model'] == 'anthropic:claude-fable-5-1'


def test_a_variable_deleted_between_the_two_reads_is_not_re_created(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.6-sol'})
    real_get = project.get_variable_config
    reads = 0

    def get_variable_config(name: str) -> Any:
        nonlocal reads
        reads += 1
        return real_get(name) if reads == 1 else None

    monkeypatch.setattr(project, 'get_variable_config', get_variable_config)
    monkeypatch.setattr(project, 'update_variable', _refuse('update_variable'))
    thread = AgentControl('checkout').publish_baseline(BASELINE)
    assert thread is not None
    with collected_warnings() as caught:
        thread.join()
    assert caught == []


def _refuse(name: str) -> Any:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise PermissionError('the variables token is read-only')

    refuse.__name__ = name
    return refuse
