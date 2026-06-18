"""Tests for the push_variables functionality."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from inline_snapshot import snapshot
from pydantic import BaseModel

import logfire
from logfire._internal.config import LogfireConfig
from logfire._internal.main import Logfire
from logfire.variables.abstract import (
    DescriptionDifference,
    LabelCompatibility,
    LabelValidationError,
    ValidationReport,
    VariableChange,
    VariableDiff,
    _apply_changes,
    _check_label_compatibility,
    _check_reference_errors,
    _check_type_label_compatibility,
    _compute_diff,
    _format_diff,
    _get_default_serialized,
    _get_json_schema,
)
from logfire.variables.config import LabeledValue, LabelRef, LatestVersion, Rollout, VariableConfig, VariablesConfig
from logfire.variables.local import LocalVariableProvider
from logfire.variables.template_validation import TemplateFieldIssue
from logfire.variables.variable import TemplateVariable, Variable


@dataclass
class MockLogfire:
    """Mock Logfire instance for testing."""

    config: Any = None
    _variables: dict[str, object] = field(default_factory=dict[str, object])

    def with_settings(self, **kwargs: Any) -> MockLogfire:
        """Return self for chaining."""
        return self


@pytest.fixture
def mock_logfire_instance() -> MockLogfire:
    """Create a mock Logfire instance."""
    return MockLogfire()


def make_logfire() -> Logfire:
    return Logfire(config=LogfireConfig())


def test_get_json_schema_bool(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for boolean type."""
    var = Variable[bool](
        name='test_bool',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    schema = _get_json_schema(var)
    assert schema == {'type': 'boolean'}


def test_get_json_schema_int(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for integer type."""
    var = Variable[int](
        name='test_int',
        default=42,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    schema = _get_json_schema(var)
    assert schema == {'type': 'integer'}


def test_get_json_schema_str(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for string type."""
    var = Variable[str](
        name='test_str',
        default='hello',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    schema = _get_json_schema(var)
    assert schema == {'type': 'string'}


def test_get_default_serialized_static(mock_logfire_instance: MockLogfire) -> None:
    """Test serialization of static default values."""
    var = Variable[int](
        name='test',
        default=42,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    serialized = _get_default_serialized(var)
    assert serialized == '42'


def test_get_default_serialized_bool(mock_logfire_instance: MockLogfire) -> None:
    """Test serialization of boolean default values."""
    var = Variable[bool](
        name='test',
        default=True,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    serialized = _get_default_serialized(var)
    assert serialized == 'true'


def test_get_default_serialized_function(mock_logfire_instance: MockLogfire) -> None:
    """Test that function defaults return None."""
    var = Variable[int](
        name='test',
        default=lambda targeting_key, attributes: 10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    serialized = _get_default_serialized(var)
    assert serialized is None


def test_check_variant_compatibility_valid(mock_logfire_instance: MockLogfire) -> None:
    """Test variant compatibility check with valid value."""
    var = Variable[int](
        name='test',
        default=0,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    result = _check_label_compatibility(var, 'test-label', '42')
    assert result.is_compatible is True
    assert result.error is None


def test_check_label_compatibility_invalid(mock_logfire_instance: MockLogfire) -> None:
    """Test label compatibility check with invalid value."""
    var = Variable[int](
        name='test',
        default=0,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    result = _check_label_compatibility(var, 'test-label', '"not an int"')
    assert result.is_compatible is False
    assert result.error is not None


def test_compute_diff_new_variable(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation for a new variable."""
    var = Variable[bool](
        name='new_feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'new_feature'
    assert diff.changes[0].change_type == 'create'
    assert diff.changes[0].initial_value == 'false'
    assert diff.has_changes is True


def test_compute_diff_no_change(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when variable exists with same schema."""
    var = Variable[bool](
        name='existing_feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'existing_feature': VariableConfig(
                name='existing_feature',
                json_schema={'type': 'boolean'},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'existing_feature'
    assert diff.changes[0].change_type == 'no_change'
    assert diff.has_changes is False


def test_compute_diff_schema_change(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when schema has changed."""
    var = Variable[int](
        name='config_value',
        default=10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'config_value': VariableConfig(
                name='config_value',
                json_schema={'type': 'string'},  # Was string, now int
                labels={
                    'default': LabeledValue(version=1, serialized_value='"hello"'),
                },
                rollout=Rollout(labels={'default': 1.0}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'config_value'
    assert diff.changes[0].change_type == 'update_schema'
    assert diff.changes[0].incompatible_labels is not None
    assert len(diff.changes[0].incompatible_labels) == 1
    assert diff.has_changes is True


def test_compute_diff_template_field_issues_local_default() -> None:
    """A local code default that references an undeclared input field surfaces as a template_field_issue."""

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{nickname}}!',  # nickname is not in Inputs
        type=str,
        inputs_type=Inputs,
    )
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([var], server_config)

    assert len(diff.template_field_issues) == 1
    issue = diff.template_field_issues[0]
    assert issue.field_name == 'nickname'
    assert issue.found_in_variable == 'prompt'
    # `None` label key represents the code default in
    # `validate_template_composition`'s contract.
    assert issue.found_in_label is None


def test_compute_diff_template_field_issues_server_label() -> None:
    """Server-stored label values are validated against the local inputs_type schema."""

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{user_name}}!',  # local default is fine
        type=str,
        inputs_type=Inputs,
    )
    # Server has a label value authored against an older schema that included
    # `nickname` — now incompatible with the local Inputs declaration.
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={
                    'type': 'object',
                    'properties': {'user_name': {'type': 'string'}, 'nickname': {'type': 'string'}},
                    'required': ['user_name'],
                },
                labels={'production': LabeledValue(version=1, serialized_value='"Hi {{nickname}}!"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    field_names = {issue.field_name for issue in diff.template_field_issues}
    labels = {issue.found_in_label for issue in diff.template_field_issues}
    assert 'nickname' in field_names
    assert 'production' in labels


def test_compute_diff_template_field_issues_follow_composition() -> None:
    """A `{{field}}` reference inside a composed-in fragment is reported with the composition path."""

    class Inputs(BaseModel):
        user_name: str

    # `prompt` composes in `fragment`, which references {{nickname}} (not declared).
    prompt = logfire.template_var(
        name='prompt',
        default='Greeting: @{fragment}@',
        type=str,
        inputs_type=Inputs,
    )
    fragment = logfire.var(
        name='fragment',
        default='Hi {{nickname}}!',
        type=str,
    )
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([prompt, fragment], server_config)

    assert any(
        issue.field_name == 'nickname'
        and issue.found_in_variable == 'fragment'
        and issue.reference_path == ['fragment']
        for issue in diff.template_field_issues
    )


def test_compute_diff_template_field_issues_reported_per_root() -> None:
    """A shared bad fragment composed by multiple template roots is reported once *per root*.

    Each root that composes the fragment is a distinct problem (the fragment is incompatible
    with each root's own `inputs_type`), so the issue must not be deduped down to a single line
    that hides which roots are affected — it carries `root_variable` to disambiguate.
    """

    class Inputs(BaseModel):
        user_name: str

    prompt_a = logfire.template_var(name='prompt_a', default='A: @{shared_fragment}@', type=str, inputs_type=Inputs)
    prompt_b = logfire.template_var(name='prompt_b', default='B: @{shared_fragment}@', type=str, inputs_type=Inputs)
    fragment = logfire.var(name='shared_fragment', default='Hi {{nickname}}!', type=str)
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([prompt_a, prompt_b, fragment], server_config)

    nickname_issues = [
        i for i in diff.template_field_issues if i.field_name == 'nickname' and i.found_in_variable == 'shared_fragment'
    ]
    assert len(nickname_issues) == 2
    assert {i.root_variable for i in nickname_issues} == {'prompt_a', 'prompt_b'}


def test_compute_diff_template_inputs_schema_change() -> None:
    """A template inputs schema change is pushed even if the value schema is unchanged."""

    class NewInputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hello {{user_name}}',
        type=str,
        inputs_type=NewInputs,
    )
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={'type': 'object', 'properties': {'old_name': {'type': 'string'}}},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    change = diff.changes[0]
    assert change.change_type == 'update_schema'
    assert change.template_inputs_schema is not None
    assert 'user_name' in change.template_inputs_schema['properties']
    # Only the template-inputs schema changed; the value's JSON schema is unchanged.
    assert change.inputs_schema_changed is True
    assert change.value_schema_changed is False
    # The diff labels precisely which schema changed instead of a generic "(schema changed)".
    assert '(template inputs schema)' in _format_diff(diff)

    provider = LocalVariableProvider(server_config)
    _apply_changes(provider, diff, server_config)
    updated_config = provider.get_variable_config('prompt')
    assert updated_config is not None
    updated_schema = updated_config.template_inputs_schema
    assert updated_schema is not None
    assert 'user_name' in updated_schema['properties']
    assert 'old_name' not in updated_schema['properties']


def test_compute_diff_value_and_inputs_schema_change() -> None:
    """When both the value schema and the template-inputs schema change, the diff labels both precisely."""

    class NewInputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hello {{user_name}}',
        type=str,
        inputs_type=NewInputs,
    )
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                # Both differ from the local variable: the value type (int vs str) and the inputs schema.
                json_schema={'type': 'integer'},
                template_inputs_schema={'type': 'object', 'properties': {'old_name': {'type': 'string'}}},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    change = diff.changes[0]
    assert change.value_schema_changed is True
    assert change.inputs_schema_changed is True
    # Both schemas changed, so the diff says so rather than picking one or printing a generic message.
    assert '(value + template inputs schema)' in _format_diff(diff)


def test_compute_diff_orphaned_variables(mock_logfire_instance: MockLogfire) -> None:
    """Test detection of orphaned server variables."""
    var = Variable[bool](
        name='my_feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'my_feature': VariableConfig(
                name='my_feature',
                json_schema={'type': 'boolean'},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            ),
            'orphan_feature': VariableConfig(
                name='orphan_feature',
                json_schema={'type': 'boolean'},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([var], server_config)

    assert 'orphan_feature' in diff.orphaned_server_variables
    assert 'my_feature' not in diff.orphaned_server_variables


def test_compute_diff_reference_errors(mock_logfire_instance: MockLogfire) -> None:
    """Reference errors include missing references and cycles."""
    var_a = Variable[str](
        name='var_a',
        default='@{missing}@ @{var_b}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    var_b = Variable[str](
        name='var_b',
        default='@{var_a}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'var_a': VariableConfig(
                name='var_a',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"@{server_missing}@"')},
                latest_version=LatestVersion(version=1, serialized_value='"@{server_latest_missing}@"'),
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
            'var_b': VariableConfig(
                name='var_b',
                json_schema={'type': 'string'},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([var_a, var_b], server_config)

    assert any("'var_a' references '@{missing}@'" in warning for warning in diff.reference_errors)
    assert any("'var_a' references '@{server_missing}@'" in warning for warning in diff.reference_errors)
    assert any("'var_a' references '@{server_latest_missing}@'" in warning for warning in diff.reference_errors)
    assert any('Reference cycle detected: var_a -> var_b -> var_a' in warning for warning in diff.reference_errors)


def test_compute_diff_reports_malformed_composition_value(mock_logfire_instance: MockLogfire) -> None:
    """Malformed/reserved `@{...}@` values are reported as reference errors, not crashes.

    `@{#if x}@` (unclosed) makes pydantic-handlebars' extractor raise a HandlebarsError, and a
    reserved literal like `@{true}@` makes it raise a bare AssertionError. Both must be caught and
    surfaced rather than crashing push/validate.
    """
    var = Variable[str](
        name='bad',
        default='@{#if x}@ unclosed',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'bad': VariableConfig(
                name='bad',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"@{true}@"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([var], server_config)  # must not raise

    parse_errors = [w for w in diff.reference_errors if 'could not be parsed' in w]
    # Both the malformed local default and the reserved-name server value are reported.
    assert any("'bad'" in w for w in parse_errors)
    assert len(parse_errors) >= 2


def test_compute_diff_reference_error_scan_handles_unserializable_default(
    mock_logfire_instance: MockLogfire,
) -> None:
    """Reference scanning tolerates defaults that cannot be serialized."""
    var = Variable[object](
        name='opaque',
        default=object(),
        type=object,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'opaque': VariableConfig(
                name='opaque',
                json_schema={},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([var], server_config)

    assert diff.reference_errors == []


def test_compute_diff_reference_error_scan_skips_already_visited_nodes(
    mock_logfire_instance: MockLogfire,
) -> None:
    """Cycle detection handles shared reference graph nodes without duplicate traversal."""
    var_a = Variable[str](
        name='var_a',
        default='@{shared}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    var_b = Variable[str](
        name='var_b',
        default='@{shared}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    shared = Variable[str](
        name='shared',
        default='value',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([var_a, var_b, shared], server_config)

    assert diff.reference_errors == []


def test_compute_diff_reference_errors_through_server_only_chain(
    mock_logfire_instance: MockLogfire,
) -> None:
    """Missing refs reached through server-only variables are surfaced.

    Reproduces the case from #1951's review: a local variable composes a
    server-only fragment whose own value references a third name that
    doesn't exist anywhere. The walker has to follow `@{ref}@` edges out
    of server-only nodes — values are in `VariablesConfig`, the walker
    just needs to follow them.
    """
    foo2 = Variable[str](
        name='foo2',
        default='@{foo1}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'foo1': VariableConfig(
                name='foo1',
                json_schema={'type': 'string'},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='"foo1 references @{foo3}@"'),
            ),
        }
    )

    diff = _compute_diff([foo2], server_config)

    assert any("'foo1' references '@{foo3}@'" in warning for warning in diff.reference_errors)


def test_compute_diff_detects_cycle_through_server_only_chain(
    mock_logfire_instance: MockLogfire,
) -> None:
    """Cycles whose midpoints are server-only are detected."""
    foo = Variable[str](
        name='foo',
        default='@{server_a}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    # foo -> server_a -> server_b -> foo (cycle, server_a and server_b
    # are server-only — no local registration).
    server_config = VariablesConfig(
        variables={
            'server_a': VariableConfig(
                name='server_a',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"@{server_b}@"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
            'server_b': VariableConfig(
                name='server_b',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"@{foo}@"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([foo], server_config)

    assert any(
        'Reference cycle detected' in warning and 'foo' in warning and 'server_a' in warning and 'server_b' in warning
        for warning in diff.reference_errors
    )


def test_format_diff_creates() -> None:
    """Test diff formatting for creates."""
    diff = VariableDiff(
        changes=[
            VariableChange(
                name='new_feature',
                change_type='create',
                local_schema={'type': 'boolean'},
                initial_value='false',
            )
        ],
        orphaned_server_variables=[],
    )
    output = _format_diff(diff)
    assert 'CREATE' in output
    assert 'new_feature' in output


def test_format_diff_updates() -> None:
    """Test diff formatting for updates."""
    diff = VariableDiff(
        changes=[
            VariableChange(
                name='updated_feature',
                change_type='update_schema',
                local_schema={'type': 'integer'},
                server_schema={'type': 'string'},
            )
        ],
        orphaned_server_variables=[],
    )
    output = _format_diff(diff)
    assert 'UPDATE' in output
    assert 'updated_feature' in output


def test_format_diff_reference_errors() -> None:
    """Reference errors are shown in the formatted diff."""
    diff = VariableDiff(
        changes=[],
        orphaned_server_variables=[],
        reference_errors=["Variable 'a' references '@{missing}@' which does not exist."],
    )

    output = _format_diff(diff)

    assert 'Reference errors' in output
    assert 'missing' in output


def test_push_non_strict_warns_undeclared_template_field(
    mock_logfire_instance: MockLogfire, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-strict push applies but warns on an undeclared `{{field}}` (renders empty at runtime)."""

    class Inputs(BaseModel):
        user_name: str

    var = TemplateVariable[str, Inputs](
        name='prompt',
        default='Hi {{user_name}}, code={{secret_code}}',
        type=str,
        inputs_type=Inputs,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    provider = LocalVariableProvider(VariablesConfig(variables={}))

    assert provider.push_variables([var], strict=False, yes=True) is True
    out = capsys.readouterr().out
    assert 'template field' in out.lower() and 'secret_code' in out
    assert 'synced successfully' not in out


def test_format_diff_reference_cycles() -> None:
    """Cycles render under a distinct blocking section, separate from missing-ref warnings."""
    diff = VariableDiff(
        changes=[],
        orphaned_server_variables=[],
        reference_errors=['Reference cycle detected: a -> b -> a'],
        reference_cycles=['Reference cycle detected: a -> b -> a'],
    )

    output = _format_diff(diff)

    assert 'Reference cycles' in output
    assert 'a -> b -> a' in output


def test_validation_report_format_reference_and_description_warnings() -> None:
    """Validation reports include informational reference and description warnings."""
    report = ValidationReport(
        errors=[],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[
            DescriptionDifference(variable_name='prompt', local_description='local', server_description=None)
        ],
        reference_errors=["Variable 'prompt' references '@{missing}@' which does not exist."],
    )

    output = report.format(colors=False)

    assert 'Validation failed' in output
    assert 'Description differences' in output
    assert 'Local:  local' in output
    assert 'Server: (none)' in output
    assert 'Reference errors' in output


def test_validation_report_reference_errors_are_invalid() -> None:
    """Reference errors make validation invalid so strict push paths can fail on cycles."""
    report = ValidationReport(
        errors=[],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
        reference_errors=['Reference cycle detected: prompt -> prompt'],
    )

    assert report.is_valid is False
    assert report.has_errors is True


def test_push_variables_strict_fails_with_reference_errors(mock_logfire_instance: MockLogfire) -> None:
    """Strict push fails when reference errors such as cycles are present."""
    provider = LocalVariableProvider(VariablesConfig(variables={}))
    var = Variable[str](
        name='prompt',
        default='@{prompt}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )

    assert provider.push_variables([var], strict=True, yes=True) is False
    assert provider.get_all_variables_config().variables == {}


def test_push_variables_blocks_cycle_even_non_strict(mock_logfire_instance: MockLogfire) -> None:
    """A cyclic reference blocks the push even in non-strict mode — it can never resolve."""
    provider = LocalVariableProvider(VariablesConfig(variables={}))
    var = Variable[str](
        name='prompt',
        default='@{prompt}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )

    assert provider.push_variables([var], strict=False, yes=True) is False
    # Nothing was applied — a known-broken cyclic variable is not published.
    assert provider.get_all_variables_config().variables == {}


def test_push_variables_warns_but_applies_missing_ref_non_strict(
    mock_logfire_instance: MockLogfire, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing (non-cyclic) reference is a non-strict warning; the push still applies.

    Unlike a cycle, a missing reference may legitimately resolve in another codebase/environment,
    so non-strict push applies it — but surfaces a prominent warning and does *not* advertise a
    clean "synced successfully".
    """
    provider = LocalVariableProvider(VariablesConfig(variables={}))
    var = Variable[str](
        name='prompt',
        default='Hello @{missing}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )

    assert provider.push_variables([var], strict=False, yes=True) is True
    out = capsys.readouterr().out
    assert 'Warning' in out and 'missing' in out
    assert 'synced successfully' not in out
    assert 'prompt' in provider.get_all_variables_config().variables


def test_push_variables_strict_fails_with_missing_reference(
    mock_logfire_instance: MockLogfire, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing (non-cyclic) reference is a hard error under strict and applies nothing.

    Non-strict only warns (the ref may resolve elsewhere); strict treats it as a blocking error — a
    different path from the unconditional cycle block above.
    """
    provider = LocalVariableProvider(VariablesConfig(variables={}))
    var = Variable[str](
        name='prompt',
        default='Hello @{missing}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )

    assert provider.push_variables([var], strict=True, yes=True) is False
    out = capsys.readouterr().out
    assert 'Reference errors found' in out
    assert provider.get_all_variables_config().variables == {}


def test_check_reference_errors_recursion_limit(mock_logfire_instance: MockLogfire) -> None:
    """A reference chain deeper than the recursion limit is surfaced as a clean error, not a crash.

    Cycle detection walks the assembled graph with a recursive DFS; an arbitrarily deep `@{ref}@`
    chain from server config would otherwise raise RecursionError out of push / validate. The chain
    is sized off the live limit so it overflows regardless of any ambient `setrecursionlimit`.
    """
    depth = sys.getrecursionlimit() + 500
    # Local seed a0 -> a1; a1..a{depth-1} are server-only links; a{depth} terminates the chain.
    seed = Variable[str](
        name='a0',
        default='@{a1}@',
        type=str,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    variables: dict[str, VariableConfig] = {}
    for i in range(1, depth):
        variables[f'a{i}'] = VariableConfig(
            name=f'a{i}',
            latest_version=LatestVersion(version=1, serialized_value=f'"@{{a{i + 1}}}@"'),
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
        )
    variables[f'a{depth}'] = VariableConfig(
        name=f'a{depth}',
        latest_version=LatestVersion(version=1, serialized_value='"leaf"'),
        labels={},
        rollout=Rollout(labels={}),
        overrides=[],
    )
    server_config = VariablesConfig(variables=variables)

    errors, cycles = _check_reference_errors([seed], server_config)
    assert any('too deeply nested' in message for message in errors)
    assert any('too deeply nested' in message for message in cycles)


def test_format_diff_template_field_issues() -> None:
    """Template field issues are shown in the formatted diff, with label and composition path when present."""
    diff = VariableDiff(
        changes=[],
        orphaned_server_variables=[],
        template_field_issues=[
            TemplateFieldIssue(
                field_name='nickname',
                found_in_variable='prompt',
                found_in_label=None,
                reference_path=[],
                root_variable='prompt',
            ),
            TemplateFieldIssue(
                field_name='nickname',
                found_in_variable='fragment',
                found_in_label='production',
                reference_path=['fragment'],
                root_variable='prompt',
            ),
        ],
    )

    output = _format_diff(diff)

    assert 'Template field issues' in output
    # A field directly in the root variable's own value.
    assert "prompt: {{nickname}} is not declared in prompt's inputs_type schema" in output
    # A field reached through composition names the root, the fragment it was found in, and the path.
    assert (
        'prompt: {{nickname}} found in fragment (label: production) via @{fragment}@ '
        "is not declared in prompt's inputs_type schema"
    ) in output


def test_format_diff_template_field_issues_multi_hop_chain() -> None:
    """A multi-hop composition path renders each ref as a complete @{...}@ token.

    Regression: the chain f-string used to drop the interior closing '@' (e.g. '@{mid} -> @{leaf}@').
    """
    diff = VariableDiff(
        changes=[],
        orphaned_server_variables=[],
        template_field_issues=[
            TemplateFieldIssue(
                field_name='nickname',
                found_in_variable='leaf',
                found_in_label=None,
                reference_path=['mid', 'leaf'],
                root_variable='top',
            ),
        ],
    )

    output = _format_diff(diff)

    assert 'via @{mid}@ -> @{leaf}@' in output
    assert '@{mid} ->' not in output  # the old malformed (missing-'@') form


def test_validation_report_format_template_field_issues() -> None:
    """ValidationReport.format() includes a section for template_field_issues with label and composition path."""
    report = ValidationReport(
        errors=[],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
        template_field_issues=[
            TemplateFieldIssue(
                field_name='nickname',
                found_in_variable='prompt',
                found_in_label=None,
                reference_path=[],
                root_variable='prompt',
            ),
            TemplateFieldIssue(
                field_name='nickname',
                found_in_variable='fragment',
                found_in_label='production',
                reference_path=['fragment'],
                root_variable='prompt',
            ),
        ],
    )

    output = report.format(colors=False)

    assert 'Template field issues' in output
    assert "prompt: {{nickname}} is not declared in prompt's inputs_type schema" in output
    assert (
        'prompt: {{nickname}} found in fragment (label: production) via @{fragment}@ '
        "is not declared in prompt's inputs_type schema"
    ) in output
    assert 'Validation failed' in output
    assert report.is_valid is False


def test_push_variables_strict_fails_with_template_field_issues() -> None:
    """Strict push fails when template field issues are present, leaving the provider unchanged."""

    class Inputs(BaseModel):
        user_name: str

    provider = LocalVariableProvider(VariablesConfig(variables={}))
    var = logfire.template_var(
        name='prompt',
        default='Hi {{nickname}}!',  # nickname is not in Inputs
        type=str,
        inputs_type=Inputs,
    )

    assert provider.push_variables([var], strict=True, yes=True) is False
    assert provider.get_all_variables_config().variables == {}


def test_compute_diff_template_field_issues_skips_label_refs() -> None:
    """LabelRef entries in server labels are skipped when collecting serialized values for validation."""

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{user_name}}!',
        type=str,
        inputs_type=Inputs,
    )
    # `staging` is a LabelRef pointing at `production` — only the LabeledValue should be
    # walked when checking template fields.
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={'type': 'object', 'properties': {'user_name': {'type': 'string'}}},
                labels={
                    'production': LabeledValue(version=1, serialized_value='"Hi {{user_name}}!"'),
                    'staging': LabelRef(version=1, ref='production'),
                },
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert diff.template_field_issues == []


def test_compute_diff_template_field_issues_tolerates_unserializable_composed_ref():
    """A composed-in variable with an unserializable default doesn't crash template-field validation."""

    # `fragment.default = object()` is not JSON-serializable; the walker should swallow
    # the dump_json error and continue.
    fragment = logfire.var(
        name='fragment',
        default=object(),
        type=object,
    )
    # Fragment lives on the server so `_compute_diff` skips its serialize-default path;
    # we want `_collect_template_field_issues` to be the one that exercises dump_json.
    server_config = VariablesConfig(
        variables={
            'fragment': VariableConfig(
                name='fragment',
                json_schema={},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([fragment], server_config)

    # No crash — the fragment's default is silently skipped, no template issues surface from it.
    assert diff == snapshot(
        VariableDiff(
            changes=[VariableChange(name='fragment', change_type='no_change')],
            orphaned_server_variables=[],
        )
    )


def test_compute_diff_template_field_issues_from_latest_version() -> None:
    """A server `latest_version` value (without label coverage) is validated against the local inputs_type."""

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{user_name}}!',
        type=str,
        inputs_type=Inputs,
    )
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={'type': 'object', 'properties': {'user_name': {'type': 'string'}}},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='"Hi {{nickname}}!"'),
            )
        }
    )

    diff = _compute_diff([var], server_config)

    field_names = {issue.field_name for issue in diff.template_field_issues}
    labels = {issue.found_in_label for issue in diff.template_field_issues}
    assert 'nickname' in field_names
    assert 'latest' in labels  # latest_version is keyed under the reserved 'latest' label


def test_compute_diff_template_field_issues_code_default_with_latest_version() -> None:
    """The local code default is validated even when the server has a `latest_version`.

    Regression test for the case where both competed for the `None` key: the code default
    used to be dropped whenever a `latest_version` existed, so an invalid code default slipped
    past push validation — even though it can still be served at runtime (empty rollout /
    `code_default` routing). The code default is now keyed `None` independently.
    """

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{local_missing}}!',  # invalid: references an undeclared field
        type=str,
        inputs_type=Inputs,
    )
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={'type': 'object', 'properties': {'user_name': {'type': 'string'}}},
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='"Hi {{user_name}}!"'),  # valid
            )
        }
    )

    diff = _compute_diff([var], server_config)

    issues = {(issue.field_name, issue.found_in_label) for issue in diff.template_field_issues}
    assert ('local_missing', None) in issues  # code default validated under None despite latest_version


def test_compute_diff_template_field_issues_label_ref_reported_against_label() -> None:
    """A `LabelRef` is followed and the issue is reported against the label that serves the value."""

    class Inputs(BaseModel):
        user_name: str

    var = logfire.template_var(
        name='prompt',
        default='Hi {{user_name}}!',  # valid local default
        type=str,
        inputs_type=Inputs,
    )
    server_config = VariablesConfig(
        variables={
            'prompt': VariableConfig(
                name='prompt',
                json_schema={'type': 'string'},
                template_inputs_schema={'type': 'object', 'properties': {'user_name': {'type': 'string'}}},
                # production pinned to latest; fallback routes to the code default (resolves to None)
                labels={'production': LabelRef(ref='latest'), 'fallback': LabelRef(ref='code_default')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=2, serialized_value='"Hi {{nickname}}!"'),  # invalid
            )
        }
    )

    diff = _compute_diff([var], server_config)

    issues = {(issue.field_name, issue.found_in_label) for issue in diff.template_field_issues}
    # The invalid latest value is served via the `production` ref and reported against that label
    # (previously LabelRefs were skipped entirely), as well as the reserved 'latest' key. The
    # `fallback` label refs the code default and resolves to None, so it contributes no value.
    assert ('nickname', 'production') in issues
    assert ('nickname', 'latest') in issues
    assert 'fallback' not in {label for _, label in issues}


def test_compute_diff_template_field_issues_skips_resolve_function_default() -> None:
    """A template variable whose code default is a resolve function isn't statically validated."""

    class Inputs(BaseModel):
        user_name: str

    def make_default(targeting_key: str | None, attributes: Any) -> str:
        return 'Hi {{user_name}}!'

    var = logfire.template_var(
        name='prompt',
        default=make_default,
        type=str,
        inputs_type=Inputs,
    )

    # No server config and a dynamic (resolve-function) default: nothing to validate statically.
    diff = _compute_diff([var], VariablesConfig(variables={}))
    assert diff.template_field_issues == []


def test_variable_diff_has_changes_true() -> None:
    """Test has_changes when there are changes."""
    diff = VariableDiff(
        changes=[
            VariableChange(name='test', change_type='create'),
        ],
        orphaned_server_variables=[],
    )
    assert diff.has_changes is True


def test_variable_diff_has_changes_false() -> None:
    """Test has_changes when there are no changes."""
    diff = VariableDiff(
        changes=[
            VariableChange(name='test', change_type='no_change'),
        ],
        orphaned_server_variables=[],
    )
    assert diff.has_changes is False


def test_push_variables_no_variables() -> None:
    """Test push_variables with no variables."""
    # Use an explicit empty list to avoid picking up variables from the global DEFAULT_LOGFIRE_INSTANCE
    result = logfire.variables_push([])
    assert result is False


def test_var_registers_variable() -> None:
    """Test that var() registers variables with the logfire instance."""
    lf = make_logfire()
    assert lf.variables_get() == []

    var1 = lf.var(name='test_var_1', default=True, type=bool)
    assert len(lf.variables_get()) == 1
    assert lf.variables_get()[0] is var1

    var2 = lf.var(name='test_var_2', default=42, type=int)
    assert len(lf.variables_get()) == 2
    assert var2 in lf.variables_get()


def test_get_variables_returns_all_registered() -> None:
    """Test that get_variables returns all registered variables."""
    lf = make_logfire()
    var1 = lf.var(name='feature_a', default=False, type=bool)
    var2 = lf.var(name='feature_b', default='hello', type=str)
    var3 = lf.var(name='feature_c', default=100, type=int)

    variables = lf.variables_get()
    assert len(variables) == 3
    assert var1 in variables
    assert var2 in variables
    assert var3 in variables


def test_with_settings_shares_registered_variables() -> None:
    """Variables registered on with_settings() siblings share one config registry."""
    lf = make_logfire()
    lf2 = lf.with_settings(tags=['other'])

    var1 = lf.var(name='feature_a', default=False, type=bool)
    var2 = lf2.var(name='feature_b', default='hello', type=str)

    assert lf.variables_get() == [var1, var2]
    assert lf2.variables_get() == [var1, var2]


def test_with_settings_duplicate_variable_names_conflict() -> None:
    """Duplicate variable names are rejected across with_settings() siblings."""
    lf = make_logfire()
    lf2 = lf.with_settings(tags=['other'])

    lf.var(name='feature_enabled', default=False, type=bool)
    with pytest.raises(ValueError, match="A variable with name 'feature_enabled' has already been registered"):
        lf2.var(name='feature_enabled', default=True, type=bool)


def test_variables_clear_clears_with_settings_siblings() -> None:
    """variables_clear() clears the shared config registry."""
    lf = make_logfire()
    lf2 = lf.with_settings(tags=['other'])

    lf.var(name='feature_a', default=False, type=bool)
    lf2.var(name='feature_b', default='hello', type=str)

    lf.variables_clear()

    assert lf.variables_get() == []
    assert lf2.variables_get() == []


# --- Validation tests ---


def test_validation_report_is_valid_false_with_errors() -> None:
    """Test is_valid when there are validation errors."""
    report = ValidationReport(
        errors=[
            LabelValidationError(
                variable_name='test',
                label='default',
                error=ValueError('invalid'),
            )
        ],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
    )
    assert not report.is_valid


def test_validation_report_is_valid_false_with_missing() -> None:
    """Test is_valid when there are missing variables."""
    report = ValidationReport(
        errors=[],
        variables_checked=1,
        variables_not_on_server=['missing-var'],
        description_differences=[],
    )
    assert not report.is_valid


def test_validation_report_is_valid_true() -> None:
    """Test is_valid when there are no errors."""
    report = ValidationReport(
        errors=[],
        variables_checked=2,
        variables_not_on_server=[],
        description_differences=[],
    )
    assert report.is_valid


def test_format_validation_report_with_errors() -> None:
    """Test validation report formatting with errors."""
    report = ValidationReport(
        errors=[
            LabelValidationError(
                variable_name='my_feature',
                label='default',
                error=ValueError('value is not valid'),
            )
        ],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
    )
    output = report.format()
    assert 'Validation Errors' in output
    assert 'my_feature' in output
    assert 'default' in output


def test_format_validation_report_with_missing() -> None:
    """Test validation report formatting with missing variables."""
    report = ValidationReport(
        errors=[],
        variables_checked=2,
        variables_not_on_server=['missing-feature'],
        description_differences=[],
    )
    output = report.format()
    assert 'Not Found on Server' in output
    assert 'missing-feature' in output


def test_format_validation_report_all_valid() -> None:
    """Test validation report formatting when all valid."""
    report = ValidationReport(
        errors=[],
        variables_checked=3,
        variables_not_on_server=[],
        description_differences=[],
    )
    output = report.format()
    assert 'Valid (3 variables)' in output


def test_validate_variables_no_variables() -> None:
    """Test validate_variables with no variables."""
    # Use an explicit empty list to avoid picking up variables from the global DEFAULT_LOGFIRE_INSTANCE
    result = logfire.variables_validate([])
    assert result.errors == []  # No variables to validate means no errors


def test_compute_diff_schema_change_with_ref_label(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when schema changes and a label uses a ref (serialized_value=None)."""
    var = Variable[int](
        name='config_value',
        default=10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'config_value': VariableConfig(
                name='config_value',
                json_schema={'type': 'string'},  # Was string, now int
                labels={
                    'v1': LabeledValue(version=1, serialized_value='"hello"'),
                    'v2': LabelRef(version=2, ref='v1'),
                },
                rollout=Rollout(labels={'v1': 1.0}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].change_type == 'update_schema'
    # Only v1 should be checked (v2 has serialized_value=None due to ref)
    assert diff.changes[0].incompatible_labels is not None
    assert len(diff.changes[0].incompatible_labels) == 1
    assert diff.changes[0].incompatible_labels[0].label == 'v1'


def test_compute_diff_schema_change_with_latest_version_incompatible(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when schema changes and latest_version value is incompatible."""
    from logfire.variables.config import LatestVersion

    var = Variable[int](
        name='config_value',
        default=10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'config_value': VariableConfig(
                name='config_value',
                json_schema={'type': 'string'},  # Was string, now int
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
                latest_version=LatestVersion(version=3, serialized_value='"not_an_int"'),
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].change_type == 'update_schema'
    assert diff.changes[0].incompatible_labels is not None
    # The latest version value is incompatible
    assert any(c.label == 'latest' for c in diff.changes[0].incompatible_labels)


def test_compute_diff_schema_change_with_latest_version_compatible(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when schema changes and latest_version value is compatible."""
    from logfire.variables.config import LatestVersion

    var = Variable[int](
        name='config_value',
        default=10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'config_value': VariableConfig(
                name='config_value',
                json_schema={'type': 'string'},  # Was string, now int
                labels={},
                rollout=Rollout(labels={}),
                overrides=[],
                latest_version=LatestVersion(version=3, serialized_value='42'),
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].change_type == 'update_schema'
    # The latest version value is compatible, so no incompatible labels
    assert diff.changes[0].incompatible_labels is None


# =============================================================================
# Test _format_diff with unchanged variables having incompatible labels
# =============================================================================


def test_format_diff_unchanged_with_incompatible_labels() -> None:
    """Test diff formatting for unchanged variables with incompatible label values (lines 538-543)."""
    diff = VariableDiff(
        changes=[
            VariableChange(
                name='my_var',
                change_type='no_change',
                incompatible_labels=[
                    LabelCompatibility(
                        label='v1',
                        serialized_value='"bad_value"',
                        is_compatible=False,
                        error='validation error',
                    ),
                ],
            )
        ],
        orphaned_server_variables=[],
    )
    output = _format_diff(diff)
    assert 'Validation warnings (schema unchanged)' in output
    assert 'my_var' in output
    assert 'Incompatible label values' in output
    assert 'v1' in output
    assert 'validation error' in output


# =============================================================================
# Test _check_type_label_compatibility
# =============================================================================


def test_check_type_label_compatibility_with_incompatible_labels() -> None:
    """Test _check_type_label_compatibility with incompatible labeled values (lines 380-411)."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(int)
    server_var = VariableConfig(
        name='my_var',
        labels={
            'v1': LabeledValue(version=1, serialized_value='"not_an_int"'),
            'v2': LabeledValue(version=2, serialized_value='42'),
            'v3': LabelRef(version=3, ref='v2'),  # LabelRef should be skipped
        },
        rollout=Rollout(labels={'v1': 0.5, 'v2': 0.5}),
        overrides=[],
    )
    incompatible = _check_type_label_compatibility(adapter, server_var)
    assert len(incompatible) == 1
    assert incompatible[0].label == 'v1'
    assert incompatible[0].is_compatible is False


def test_check_type_label_compatibility_with_incompatible_latest_version() -> None:
    """Test _check_type_label_compatibility with incompatible latest_version (lines 399-410)."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(int)
    server_var = VariableConfig(
        name='my_var',
        labels={},
        rollout=Rollout(labels={}),
        overrides=[],
        latest_version=LatestVersion(version=1, serialized_value='"not_an_int"'),
    )
    incompatible = _check_type_label_compatibility(adapter, server_var)
    assert len(incompatible) == 1
    assert incompatible[0].label == 'latest'
    assert incompatible[0].is_compatible is False


def test_check_type_label_compatibility_all_compatible() -> None:
    """Test _check_type_label_compatibility when all values are compatible."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(int)
    server_var = VariableConfig(
        name='my_var',
        labels={'v1': LabeledValue(version=1, serialized_value='42')},
        rollout=Rollout(labels={'v1': 1.0}),
        overrides=[],
        latest_version=LatestVersion(version=1, serialized_value='100'),
    )
    incompatible = _check_type_label_compatibility(adapter, server_var)
    assert incompatible == []
