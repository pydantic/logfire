"""Tests for the push_variables functionality."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import logfire
from logfire.variables.config import Rollout, VariableConfig, VariablesConfig, Variant
from logfire.variables.push import (
    ValidationReport,
    VariableChange,
    VariableDiff,
    VariantValidationError,
    _check_variant_compatibility,
    _compute_diff,
    _format_diff,
    _format_validation_report,
    _get_default_serialized,
    _get_json_schema,
)
from logfire.variables.variable import Variable


@dataclass
class MockLogfire:
    """Mock Logfire instance for testing."""

    config: Any = None

    def with_settings(self, **kwargs: Any) -> MockLogfire:
        """Return self for chaining."""
        return self


@pytest.fixture
def mock_logfire_instance() -> MockLogfire:
    """Create a mock Logfire instance."""
    return MockLogfire()


def test_get_json_schema_bool(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for boolean type."""
    var = Variable[bool](
        name='test-bool',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    schema = _get_json_schema(var)
    assert schema == {'type': 'boolean'}


def test_get_json_schema_int(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for integer type."""
    var = Variable[int](
        name='test-int',
        default=42,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    schema = _get_json_schema(var)
    assert schema == {'type': 'integer'}


def test_get_json_schema_str(mock_logfire_instance: MockLogfire) -> None:
    """Test JSON schema generation for string type."""
    var = Variable[str](
        name='test-str',
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
    result = _check_variant_compatibility(var, 'test-variant', '42')
    assert result.is_compatible is True
    assert result.error is None


def test_check_variant_compatibility_invalid(mock_logfire_instance: MockLogfire) -> None:
    """Test variant compatibility check with invalid value."""
    var = Variable[int](
        name='test',
        default=0,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    result = _check_variant_compatibility(var, 'test-variant', '"not an int"')
    assert result.is_compatible is False
    assert result.error is not None


def test_compute_diff_new_variable(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation for a new variable."""
    var = Variable[bool](
        name='new-feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(variables={})

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'new-feature'
    assert diff.changes[0].change_type == 'create'
    assert diff.changes[0].initial_variant_value == 'false'
    assert diff.has_changes is True


def test_compute_diff_no_change(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when variable exists with same schema."""
    var = Variable[bool](
        name='existing-feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'existing-feature': VariableConfig(
                name='existing-feature',
                json_schema={'type': 'boolean'},
                variants={},
                rollout=Rollout(variants={}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'existing-feature'
    assert diff.changes[0].change_type == 'no_change'
    assert diff.has_changes is False


def test_compute_diff_schema_change(mock_logfire_instance: MockLogfire) -> None:
    """Test diff computation when schema has changed."""
    var = Variable[int](
        name='config-value',
        default=10,
        type=int,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'config-value': VariableConfig(
                name='config-value',
                json_schema={'type': 'string'},  # Was string, now int
                variants={
                    'default': Variant(key='default', serialized_value='"hello"'),
                },
                rollout=Rollout(variants={'default': 1.0}),
                overrides=[],
            )
        }
    )

    diff = _compute_diff([var], server_config)

    assert len(diff.changes) == 1
    assert diff.changes[0].name == 'config-value'
    assert diff.changes[0].change_type == 'update_schema'
    assert diff.changes[0].incompatible_variants is not None
    assert len(diff.changes[0].incompatible_variants) == 1
    assert diff.has_changes is True


def test_compute_diff_orphaned_variables(mock_logfire_instance: MockLogfire) -> None:
    """Test detection of orphaned server variables."""
    var = Variable[bool](
        name='my-feature',
        default=False,
        type=bool,
        logfire_instance=mock_logfire_instance,  # type: ignore
    )
    server_config = VariablesConfig(
        variables={
            'my-feature': VariableConfig(
                name='my-feature',
                json_schema={'type': 'boolean'},
                variants={},
                rollout=Rollout(variants={}),
                overrides=[],
            ),
            'orphan-feature': VariableConfig(
                name='orphan-feature',
                json_schema={'type': 'boolean'},
                variants={},
                rollout=Rollout(variants={}),
                overrides=[],
            ),
        }
    )

    diff = _compute_diff([var], server_config)

    assert 'orphan-feature' in diff.orphaned_server_variables
    assert 'my-feature' not in diff.orphaned_server_variables


def test_format_diff_creates() -> None:
    """Test diff formatting for creates."""
    diff = VariableDiff(
        changes=[
            VariableChange(
                name='new-feature',
                change_type='create',
                local_schema={'type': 'boolean'},
                initial_variant_value='false',
            )
        ],
        orphaned_server_variables=[],
    )
    output = _format_diff(diff)
    assert 'CREATE' in output
    assert 'new-feature' in output


def test_format_diff_updates() -> None:
    """Test diff formatting for updates."""
    diff = VariableDiff(
        changes=[
            VariableChange(
                name='updated-feature',
                change_type='update_schema',
                local_schema={'type': 'integer'},
                server_schema={'type': 'string'},
            )
        ],
        orphaned_server_variables=[],
    )
    output = _format_diff(diff)
    assert 'UPDATE' in output
    assert 'updated-feature' in output


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
    result = logfire.push_variables([])
    assert result is False


def test_var_registers_variable() -> None:
    """Test that var() registers variables with the logfire instance."""
    from logfire._internal.main import Logfire

    lf = Logfire()
    assert lf.get_variables() == []

    var1 = lf.var(name='test-var-1', default=True, type=bool)
    assert len(lf.get_variables()) == 1
    assert lf.get_variables()[0] is var1

    var2 = lf.var(name='test-var-2', default=42, type=int)
    assert len(lf.get_variables()) == 2
    assert var2 in lf.get_variables()


def test_get_variables_returns_all_registered() -> None:
    """Test that get_variables returns all registered variables."""
    from logfire._internal.main import Logfire

    lf = Logfire()
    var1 = lf.var(name='feature-a', default=False, type=bool)
    var2 = lf.var(name='feature-b', default='hello', type=str)
    var3 = lf.var(name='feature-c', default=100, type=int)

    variables = lf.get_variables()
    assert len(variables) == 3
    assert var1 in variables
    assert var2 in variables
    assert var3 in variables


# --- Validation tests ---


def test_validation_report_has_errors_true_with_errors() -> None:
    """Test has_errors when there are validation errors."""
    report = ValidationReport(
        errors=[
            VariantValidationError(
                variable_name='test',
                variant_key='default',
                error=ValueError('invalid'),
            )
        ],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
    )
    assert report.has_errors is True


def test_validation_report_has_errors_true_with_missing() -> None:
    """Test has_errors when there are missing variables."""
    report = ValidationReport(
        errors=[],
        variables_checked=1,
        variables_not_on_server=['missing-var'],
        description_differences=[],
    )
    assert report.has_errors is True


def test_validation_report_has_errors_false() -> None:
    """Test has_errors when there are no errors."""
    report = ValidationReport(
        errors=[],
        variables_checked=2,
        variables_not_on_server=[],
        description_differences=[],
    )
    assert report.has_errors is False


def test_format_validation_report_with_errors() -> None:
    """Test validation report formatting with errors."""
    report = ValidationReport(
        errors=[
            VariantValidationError(
                variable_name='my-feature',
                variant_key='default',
                error=ValueError('value is not valid'),
            )
        ],
        variables_checked=1,
        variables_not_on_server=[],
        description_differences=[],
    )
    output = _format_validation_report(report)
    assert 'Validation Errors' in output
    assert 'my-feature' in output
    assert 'default' in output


def test_format_validation_report_with_missing() -> None:
    """Test validation report formatting with missing variables."""
    report = ValidationReport(
        errors=[],
        variables_checked=2,
        variables_not_on_server=['missing-feature'],
        description_differences=[],
    )
    output = _format_validation_report(report)
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
    output = _format_validation_report(report)
    assert 'Valid (3 variables)' in output


def test_validate_variables_no_variables() -> None:
    """Test validate_variables with no variables."""
    # Use an explicit empty list to avoid picking up variables from the global DEFAULT_LOGFIRE_INSTANCE
    result = logfire.validate_variables([])
    assert result is True  # No variables to validate is success
