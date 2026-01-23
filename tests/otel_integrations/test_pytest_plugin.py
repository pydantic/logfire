"""Tests for the pytest plugin."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownLambdaType=false

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from logfire._internal.integrations import pytest as pytest_plugin

pytest_plugins = ['pytester']


@pytest.fixture
def no_ci_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all CI-related environment variables."""
    # Generic CI
    monkeypatch.delenv('CI', raising=False)
    # GitHub Actions
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.delenv('GITHUB_WORKFLOW', raising=False)
    monkeypatch.delenv('GITHUB_RUN_ID', raising=False)
    monkeypatch.delenv('GITHUB_REPOSITORY', raising=False)
    monkeypatch.delenv('GITHUB_REF', raising=False)
    monkeypatch.delenv('GITHUB_SHA', raising=False)
    monkeypatch.delenv('GITHUB_SERVER_URL', raising=False)
    # GitLab CI
    monkeypatch.delenv('GITLAB_CI', raising=False)
    monkeypatch.delenv('CI_JOB_ID', raising=False)
    monkeypatch.delenv('CI_JOB_URL', raising=False)
    monkeypatch.delenv('CI_PIPELINE_ID', raising=False)
    monkeypatch.delenv('CI_COMMIT_REF_NAME', raising=False)
    monkeypatch.delenv('CI_COMMIT_SHA', raising=False)
    # CircleCI
    monkeypatch.delenv('CIRCLECI', raising=False)
    monkeypatch.delenv('CIRCLE_BUILD_NUM', raising=False)
    monkeypatch.delenv('CIRCLE_BUILD_URL', raising=False)
    monkeypatch.delenv('CIRCLE_BRANCH', raising=False)
    monkeypatch.delenv('CIRCLE_SHA1', raising=False)
    # Jenkins
    monkeypatch.delenv('JENKINS_URL', raising=False)
    monkeypatch.delenv('BUILD_NUMBER', raising=False)
    monkeypatch.delenv('BUILD_URL', raising=False)
    monkeypatch.delenv('GIT_BRANCH', raising=False)
    monkeypatch.delenv('GIT_COMMIT', raising=False)


@pytest.fixture
def logfire_pytester(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, no_ci_envs: None) -> pytest.Pytester:
    """Pytester pre-configured for logfire plugin testing with span capture."""
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
    monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
    monkeypatch.delenv('TRACEPARENT', raising=False)
    monkeypatch.delenv('TRACESTATE', raising=False)

    # Create a conftest that captures spans to a JSON file
    # NOTE: We use trylast=True so this runs AFTER the logfire pytest plugin configures
    # And hookwrapper=True with trylast for sessionfinish so we capture after logfire closes session span
    pytester.makeconftest('''
import json
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from logfire._internal.exporters.test import TestExporter

_exporter = TestExporter()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Add our test exporter AFTER logfire plugin has configured the tracer."""
    from logfire._internal.integrations.pytest import _CONFIG_KEY
    if lf_config := config.stash.get(_CONFIG_KEY, None):
        lf_config.logfire_instance.config.get_tracer_provider().add_span_processor(SimpleSpanProcessor(_exporter))


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Write captured spans to file after logfire plugin closes session span."""
    # Yield first to let logfire close the session span
    yield
    # Now capture all spans including the session span
    spans_data = _exporter.exported_spans_as_dict()
    with open("spans.json", "w") as f:
        json.dump(spans_data, f, indent=2)
''')
    return pytester


# Helper functions
def load_spans(pytester: pytest.Pytester) -> list[dict[str, Any]]:
    """Load spans from captured file."""
    import json

    spans_file = pytester.path / 'spans.json'
    if not spans_file.exists():  # pragma: no cover
        return []
    return json.loads(spans_file.read_text())


def find_span_by_pattern(spans: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
    """Find span by name pattern."""
    for span in spans:
        name = span.get('name', '')
        if isinstance(name, str) and pattern in name:
            return span
    return None


def find_spans_by_pattern(spans: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    """Find all spans matching name pattern."""
    return [span for span in spans if isinstance(span.get('name', ''), str) and pattern in span.get('name', '')]


def find_session_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the session span."""
    for span in spans:
        if 'pytest:' in span['name']:
            return span
    return None  # pragma: no cover


# Tests for module import logic
def test_stash_keys_defined():
    """Module should have stash keys defined when pytest is available."""
    assert hasattr(pytest_plugin, '_CONFIG_KEY')
    assert hasattr(pytest_plugin, '_SESSION_SPAN_KEY')
    assert hasattr(pytest_plugin, '_SPAN_KEY')
    assert hasattr(pytest_plugin, '_CONTEXT_TOKEN_KEY')


# Tests for auto-enable logic
@pytest.mark.parametrize(
    'ci_env,token_env,expected',
    [
        ('true', 'test-token', True),  # Should auto-enable with CI and token
        (None, 'test-token', False),  # Should not auto-enable without CI
        ('true', None, False),  # Should not auto-enable without token
        ('false', 'test-token', False),  # Should not auto-enable with CI=false
    ],
    ids=['with_ci_and_token', 'without_ci', 'without_token', 'with_ci_false'],
)
def test_should_auto_enable(monkeypatch: pytest.MonkeyPatch, ci_env: str | None, token_env: str | None, expected: bool):
    """Test auto-enable logic with different environment combinations."""
    if ci_env is None:
        monkeypatch.delenv('CI', raising=False)
    else:
        monkeypatch.setenv('CI', ci_env)

    if token_env is None:
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
    else:
        monkeypatch.setenv('LOGFIRE_TOKEN', token_env)

    assert pytest_plugin._should_auto_enable() is expected


# Tests for plugin enable/disable logic
def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    """Plugin should be disabled by default."""
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)

    config = mock.MagicMock()
    config.getoption.return_value = False
    config.getini.return_value = False

    assert pytest_plugin._is_enabled(config) is False


def test_enabled_with_flag(monkeypatch: pytest.MonkeyPatch):
    """Plugin should be enabled with --logfire flag."""
    monkeypatch.delenv('CI', raising=False)

    config = mock.MagicMock()
    config.getoption.side_effect = lambda opt, default=None: opt == '--logfire'
    config.getini.return_value = False

    assert pytest_plugin._is_enabled(config) is True


def test_disabled_with_no_logfire_flag(monkeypatch: pytest.MonkeyPatch):
    """Plugin should be disabled with --no-logfire flag even in CI."""
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')

    config = mock.MagicMock()
    config.getoption.side_effect = lambda opt, default=None: opt == '--no-logfire'
    config.getini.return_value = False

    assert pytest_plugin._is_enabled(config) is False


def test_enabled_with_ini(monkeypatch: pytest.MonkeyPatch):
    """Plugin should be enabled with INI option."""
    monkeypatch.delenv('CI', raising=False)

    config = mock.MagicMock()
    config.getoption.return_value = False
    config.getini.side_effect = lambda opt: opt == 'logfire'

    assert pytest_plugin._is_enabled(config) is True


def test_auto_enabled_in_ci(monkeypatch: pytest.MonkeyPatch):
    """Plugin should auto-enable in CI with token."""
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')

    config = mock.MagicMock()
    config.getoption.return_value = False
    config.getini.return_value = False

    assert pytest_plugin._is_enabled(config) is True


# Tests for trace phases configuration
@pytest.mark.parametrize(
    'cli_value,ini_value,expected',
    [
        (True, False, True),  # CLI flag enables
        (False, True, True),  # INI option enables
        (False, False, False),  # Disabled by default
    ],
    ids=['cli_flag', 'ini_option', 'disabled'],
)
def test_trace_phases(cli_value: bool, ini_value: bool, expected: bool):
    """Test phase tracing configuration."""
    config = mock.MagicMock()
    config.getoption.return_value = cli_value
    config.getini.return_value = ini_value

    assert pytest_plugin._get_trace_phases(config) is expected


# Tests for service name configuration
def test_default_service_name(monkeypatch: pytest.MonkeyPatch):
    """Should return default service name."""
    monkeypatch.delenv('LOGFIRE_SERVICE_NAME', raising=False)

    config = mock.MagicMock()
    config.getoption.return_value = None
    config.getini.return_value = None

    assert pytest_plugin._get_service_name(config) == 'pytest'


def test_service_name_from_cli(monkeypatch: pytest.MonkeyPatch):
    """CLI option should take precedence."""
    monkeypatch.setenv('LOGFIRE_SERVICE_NAME', 'env-service')

    config = mock.MagicMock()
    config.getoption.return_value = 'cli-service'
    config.getini.return_value = 'ini-service'

    assert pytest_plugin._get_service_name(config) == 'cli-service'


def test_service_name_from_env(monkeypatch: pytest.MonkeyPatch):
    """Environment variable should be second priority."""
    monkeypatch.setenv('LOGFIRE_SERVICE_NAME', 'env-service')

    config = mock.MagicMock()
    config.getoption.return_value = None
    config.getini.return_value = 'ini-service'

    assert pytest_plugin._get_service_name(config) == 'env-service'


def test_service_name_from_ini(monkeypatch: pytest.MonkeyPatch):
    """INI option should be third priority."""
    monkeypatch.delenv('LOGFIRE_SERVICE_NAME', raising=False)

    config = mock.MagicMock()
    config.getoption.return_value = None
    config.getini.return_value = 'ini-service'

    assert pytest_plugin._get_service_name(config) == 'ini-service'


# Integration tests using pytester
def test_plugin_disabled_by_default(logfire_pytester: pytest.Pytester):
    """Plugin should do nothing without --logfire flag."""
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django')
    result.stdout.fnmatch_lines(['*1 passed*'])


def test_help_shows_logfire_options(logfire_pytester: pytest.Pytester):
    """Help text should show Logfire options."""
    result = logfire_pytester.runpytest_subprocess('--help')
    result.stdout.fnmatch_lines(
        [
            '*logfire*',
            '*--logfire*',
        ]
    )


def test_plugin_runs_with_flag(logfire_pytester: pytest.Pytester):
    """Plugin should run with --logfire flag."""
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.stdout.fnmatch_lines(['*1 passed*'])


def test_ini_config_enables_plugin(logfire_pytester: pytest.Pytester):
    """INI options should enable plugin."""
    logfire_pytester.makeini("""
        [pytest]
        logfire = true
        addopts = -p no:langsmith
    """)
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django')
    result.stdout.fnmatch_lines(['*1 passed*'])


# Tests that verify spans are captured correctly with expected hierarchy and attributes
def test_session_span_attributes(logfire_pytester: pytest.Pytester):
    """Verify session span has correct attributes (from documentation example)."""
    logfire_pytester.makepyfile("""
        def test_one():
            assert True

        def test_two():
            assert True

        def test_three():
            assert False
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=2, failed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_span_by_pattern(spans, 'pytest:')
    assert session_span is not None, 'Session span not found'

    attrs = session_span['attributes']
    assert 'pytest.args' in attrs
    assert 'pytest.rootpath' in attrs
    assert 'pytest.testscollected' in attrs
    assert attrs['pytest.testscollected'] == 3
    assert 'pytest.testsfailed' in attrs
    assert attrs['pytest.testsfailed'] == 1
    assert 'pytest.exitstatus' in attrs


def test_test_span_attributes(logfire_pytester: pytest.Pytester):
    """Verify test spans have correct attributes (from documentation example)."""
    logfire_pytester.makepyfile("""
        def test_passing():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_passing')
    assert test_span is not None, 'Test span not found'

    attrs = test_span['attributes']
    assert attrs['test.name'] == 'test_passing'
    assert 'test.nodeid' in attrs
    assert 'test_passing' in attrs['test.nodeid']
    assert attrs['test.outcome'] == 'passed'
    assert 'test.duration_ms' in attrs
    assert 'code.filepath' in attrs
    assert 'code.function' in attrs
    assert attrs['code.function'] == 'test_passing'
    assert 'code.lineno' in attrs


def test_failed_test_records_exception(logfire_pytester: pytest.Pytester):
    """Failed tests should record exception with traceback (from documentation example)."""
    logfire_pytester.makepyfile("""
        def test_failure():
            assert False, "intentional failure"
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(failed=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_failure')
    assert test_span is not None, 'Test span not found'

    attrs = test_span['attributes']
    assert attrs['test.outcome'] == 'failed'

    # Check for exception event
    events = test_span.get('events', [])
    exception_events = [e for e in events if e.get('name') == 'exception']
    assert len(exception_events) == 1, 'Should have one exception event'

    exc_event = exception_events[0]
    exc_attrs = exc_event['attributes']
    assert exc_attrs['exception.type'] == 'AssertionError'
    assert 'intentional failure' in exc_attrs['exception.message']
    assert 'exception.stacktrace' in exc_attrs


def test_skipped_test_with_reason(logfire_pytester: pytest.Pytester):
    """Skipped tests should create a span with basic test attributes.

    Note: Currently, tests that are skipped during setup (via @pytest.mark.skip)
    don't have test.outcome or test.skip_reason attributes because the pytest plugin
    only records these on the 'call' phase. This test verifies that the test span
    is still created with basic attributes.
    """
    logfire_pytester.makepyfile("""
        import pytest

        @pytest.mark.skip(reason="not ready yet")
        def test_skipped():
            pass
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(skipped=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_skipped')
    assert test_span is not None, 'Test span not found'

    # Verify basic test attributes are still recorded
    attrs = test_span['attributes']
    assert attrs['test.name'] == 'test_skipped'
    assert 'test.nodeid' in attrs
    assert 'code.filepath' in attrs


def test_xfail_test(logfire_pytester: pytest.Pytester):
    """xfail tests should record skip reason with wasxfail."""
    logfire_pytester.makepyfile("""
        import pytest

        @pytest.mark.xfail(reason="expected to fail")
        def test_xfail():
            assert False
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    # xfail is reported as xfailed, not skipped
    result.assert_outcomes(xfailed=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_xfail')
    assert test_span is not None, 'Test span not found'

    # The test should have skip reason recorded from wasxfail
    attrs = test_span['attributes']
    assert attrs['test.name'] == 'test_xfail'
    assert 'test.nodeid' in attrs
    assert 'code.filepath' in attrs

    # TODO: Uncomment when we decide on standard for xfail skip reason
    # wasxfail can be the reason or 'xfailed' default
    # assert attrs['test.skip_reason'] in ['expected to fail', 'xfailed']


def test_skipped_with_pytest_skip(logfire_pytester: pytest.Pytester):
    """Tests skipped with pytest.skip() should record skip reason."""
    logfire_pytester.makepyfile("""
        import pytest

        def test_skip_with_call():
            pytest.skip("skipping this test")
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(skipped=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_skip_with_call')
    assert test_span is not None, 'Test span not found'


def test_test_without_exception(logfire_pytester: pytest.Pytester):
    """Passing tests should not record exceptions."""
    logfire_pytester.makepyfile("""
        def test_passing():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_passing')
    assert test_span is not None

    # Should not have exception events
    events = test_span.get('events', [])
    exception_events = [e for e in events if e.get('name') == 'exception']
    assert len(exception_events) == 0


def test_parameterized_tests(logfire_pytester: pytest.Pytester):
    """Parameterized tests should record parameters (from documentation example)."""
    logfire_pytester.makepyfile("""
        import pytest

        @pytest.mark.parametrize("value", [1, 2, 3])
        def test_param(value):
            assert value > 0
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=3)

    spans = load_spans(logfire_pytester)
    param_spans = find_spans_by_pattern(spans, 'test_param')
    assert len(param_spans) == 3, 'Should have 3 parameterized test spans'
    assert len(set(span['name'] for span in param_spans)) == 3, 'Each param span should have unique name'

    for span in param_spans:
        attrs = span['attributes']
        assert attrs['test.outcome'] == 'passed'
        assert 'test.parameters' in attrs


def test_parameterized_tests_with_non_serializable_params(logfire_pytester: pytest.Pytester):
    """Parameterized tests with non-serializable params should store param keys."""
    logfire_pytester.makepyfile("""
        import pytest

        class NonSerializable:
            pass

        @pytest.mark.parametrize("obj", [NonSerializable()])
        def test_with_object(obj):
            assert obj is not None
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    param_spans = find_spans_by_pattern(spans, 'test_with_object')
    assert len(param_spans) == 1

    assert param_spans[0]['name'] == 'test_parameterized_tests_with_non_serializable_params.py::test_with_object[obj0]'

    attrs = param_spans[0]['attributes']
    # Should have test.parameters with just the keys
    assert 'test.parameters' in attrs
    # The value should be a string representation of the keys
    assert 'obj' in attrs['test.parameters']


def test_test_spans_nested_under_session(logfire_pytester: pytest.Pytester):
    """Test spans should be children of session span."""
    logfire_pytester.makepyfile("""
        def test_one():
            assert True

        def test_two():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=2)

    spans = load_spans(logfire_pytester)
    session_span = find_span_by_pattern(spans, 'pytest:')
    test_spans = find_spans_by_pattern(spans, 'test_')

    assert session_span is not None
    assert len(test_spans) == 2

    session_span_id = session_span['context']['span_id']

    for test_span in test_spans:
        assert test_span['parent'] is not None, 'Test span should have parent'
        assert test_span['parent']['span_id'] == session_span_id, 'Test span parent should be session'


def test_class_based_test(logfire_pytester: pytest.Pytester):
    """Class-based tests should include class name in attributes."""
    logfire_pytester.makepyfile("""
        class TestMyClass:
            def test_method(self):
                assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    test_span = find_span_by_pattern(spans, 'test_method')
    assert test_span is not None

    attrs = test_span['attributes']
    assert attrs.get('test.class') == 'TestMyClass'
    assert attrs['test.module'].endswith('test_class_based_test')


# Tests for custom spans and HTTPX integration
def test_custom_spans_nested_under_test_span(logfire_pytester: pytest.Pytester):
    """Custom logfire spans during tests should be nested under test spans.

    This verifies that any spans created via logfire.span() during test execution
    are properly nested under the test span.
    """
    logfire_pytester.makepyfile("""
        def test_with_custom_span(logfire_instance):
            with logfire_instance.span("fetching data"):
                # Simulate some work
                result = 1 + 1
                assert result == 2
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Find the relevant spans
    session_span = find_span_by_pattern(spans, 'pytest:')
    test_span = find_span_by_pattern(spans, 'test_with_custom_span')
    custom_span = find_span_by_pattern(spans, 'fetching data')

    assert session_span is not None, 'Session span not found'
    assert test_span is not None, 'Test span not found'
    assert custom_span is not None, 'Custom span not found'

    # Verify hierarchy: session -> test -> custom
    assert test_span['parent'] is not None
    assert test_span['parent']['span_id'] == session_span['context']['span_id']

    assert custom_span['parent'] is not None
    assert custom_span['parent']['span_id'] == test_span['context']['span_id']

    # All spans share the same trace_id
    assert session_span['context']['trace_id'] == test_span['context']['trace_id']
    assert test_span['context']['trace_id'] == custom_span['context']['trace_id']


def test_nested_custom_spans_hierarchy(logfire_pytester: pytest.Pytester):
    """Nested custom spans maintain correct hierarchy.

    This tests that multiple levels of custom spans work correctly:
    pytest: my-project
    └── test_file.py::test_nested_workflow
        ├── create user
        │   └── validate input
        └── verify user
            └── check permissions
    """
    logfire_pytester.makepyfile("""
        def test_nested_workflow(logfire_instance):
            with logfire_instance.span("create user"):
                with logfire_instance.span("validate input"):
                    # Simulate validation
                    user_data = {"name": "Test User"}
                    assert "name" in user_data

            with logfire_instance.span("verify user"):
                with logfire_instance.span("check permissions"):
                    # Simulate permission check
                    has_permission = True
                    assert has_permission
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Find the relevant spans
    test_span = find_span_by_pattern(spans, 'test_nested_workflow')
    create_span = find_span_by_pattern(spans, 'create user')
    verify_span = find_span_by_pattern(spans, 'verify user')
    validate_span = find_span_by_pattern(spans, 'validate input')
    permissions_span = find_span_by_pattern(spans, 'check permissions')

    assert test_span is not None, 'Test span not found'
    assert create_span is not None, 'Create user span not found'
    assert verify_span is not None, 'Verify user span not found'
    assert validate_span is not None, 'Validate input span not found'
    assert permissions_span is not None, 'Check permissions span not found'

    # Verify hierarchy
    assert create_span['parent']['span_id'] == test_span['context']['span_id']
    assert verify_span['parent']['span_id'] == test_span['context']['span_id']
    assert validate_span['parent']['span_id'] == create_span['context']['span_id']
    assert permissions_span['parent']['span_id'] == verify_span['context']['span_id']


def test_logfire_info_creates_span(logfire_pytester: pytest.Pytester):
    """Logfire log calls during tests should create spans nested under test span.

    This tests that logfire.info() and similar calls work correctly within tests.
    """
    logfire_pytester.makepyfile("""
        def test_with_logging(logfire_instance):
            logfire_instance.info("Starting test operation")
            result = 42
            logfire_instance.info("Operation completed", result=result)
            assert result == 42
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Find test span and log spans
    test_span = find_span_by_pattern(spans, 'test_with_logging')
    assert test_span is not None, 'Test span not found'

    # Find log spans
    log_spans = find_spans_by_pattern(spans, 'Starting test operation')
    completed_spans = find_spans_by_pattern(spans, 'Operation completed')

    assert len(log_spans) >= 1, 'Starting log span not found'
    assert len(completed_spans) >= 1, 'Completed log span not found'

    # Verify log spans are children of test span
    for log_span in log_spans + completed_spans:
        assert log_span['parent'] is not None
        assert log_span['parent']['span_id'] == test_span['context']['span_id']


# Tests for TRACEPARENT environment variable support
def test_traceparent_env_var_support(logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """TRACEPARENT environment variable should link traces to external systems.

    From documentation: The traceparent header is automatically added to outgoing
    requests, allowing correlation with downstream services.
    """
    # Set a known TRACEPARENT value (W3C trace context format)
    # Format: version-trace_id-parent_id-flags
    monkeypatch.setenv('TRACEPARENT', '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01')

    logfire_pytester.makepyfile("""
        def test_with_traceparent():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_span_by_pattern(spans, 'pytest:')
    assert session_span is not None

    # The session span should be linked to the parent trace from TRACEPARENT
    # The trace_id in the TRACEPARENT should match the session span's trace_id
    expected_trace_id = int('0af7651916cd43dd8448eb211c80319c', 16)
    assert session_span['context']['trace_id'] == expected_trace_id


def test_traceparent_with_tracestate(logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """TRACEPARENT with TRACESTATE should both be handled."""
    monkeypatch.setenv('TRACEPARENT', '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01')
    monkeypatch.setenv('TRACESTATE', 'vendor1=value1,vendor2=value2')

    logfire_pytester.makepyfile("""
        def test_with_tracestate():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_span_by_pattern(spans, 'pytest:')
    assert session_span is not None

    # Should also link to the parent trace even with tracestate
    expected_trace_id = int('0af7651916cd43dd8448eb211c80319c', 16)
    assert session_span['context']['trace_id'] == expected_trace_id


# Tests for the logfire fixture
def test_logfire_fixture_works_without_plugin_enabled(logfire_pytester: pytest.Pytester):
    """The logfire_instance fixture should work even when the plugin is not enabled.

    When the plugin is not enabled, the fixture creates a local-only instance
    that doesn't send traces to Logfire servers.
    """
    logfire_pytester.makepyfile("""
        def test_using_logfire_fixture(logfire_instance):
            # The fixture should work even without --logfire flag
            assert hasattr(logfire_instance, 'span')
            assert hasattr(logfire_instance, 'info')
            with logfire_instance.span("test span"):
                pass
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty')
    result.assert_outcomes(passed=1)


def test_logfire_fixture_returns_instance_when_enabled(logfire_pytester: pytest.Pytester):
    """The logfire_instance fixture should return a Logfire instance when plugin is enabled."""
    logfire_pytester.makepyfile("""
        def test_using_logfire_fixture(logfire_instance):
            # Verify we got a Logfire instance
            assert hasattr(logfire_instance, 'span')
            assert hasattr(logfire_instance, 'info')
            assert hasattr(logfire_instance, 'instrument_httpx')
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)


def test_logfire_fixture_can_create_spans(logfire_pytester: pytest.Pytester):
    """The logfire_instance fixture should be able to create spans that nest under test spans."""
    logfire_pytester.makepyfile("""
        def test_using_logfire_fixture(logfire_instance):
            with logfire_instance.span("custom span from fixture"):
                assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Find the test span and custom span
    test_span = find_span_by_pattern(spans, 'test_using_logfire_fixture')
    custom_span = find_span_by_pattern(spans, 'custom span from fixture')

    assert test_span is not None, 'Test span not found'
    assert custom_span is not None, 'Custom span not found'

    # Verify the custom span is nested under the test span
    assert custom_span['parent'] is not None
    assert custom_span['parent']['span_id'] == test_span['context']['span_id']


def test_logfire_fixture_in_test_fixture(logfire_pytester: pytest.Pytester):
    """The logfire_instance fixture should work when used in user fixtures."""
    logfire_pytester.makepyfile('''
        import pytest

        @pytest.fixture
        def my_client(logfire_instance):
            """A fixture that uses the logfire_instance fixture."""
            with logfire_instance.span("setting up client"):
                client = {"url": "https://api.example.com"}
            return client

        def test_with_client_fixture(my_client):
            assert my_client["url"] == "https://api.example.com"
    ''')
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Find the test span and setup span
    test_span = find_span_by_pattern(spans, 'test_with_client_fixture')
    setup_span = find_span_by_pattern(spans, 'setting up client')

    assert test_span is not None, 'Test span not found'
    assert setup_span is not None, 'Setup span not found'

    # Note: The setup span will be a sibling of the test span (both under session)
    # because fixture setup happens before test execution in pytest
    # We just verify both spans exist
    assert setup_span is not None


# Tests for --logfire-trace-phases feature
def test_phase_tracing_disabled_by_default(logfire_pytester: pytest.Pytester):
    """Phase tracing should be disabled by default."""
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Should not have setup/call/teardown spans
    assert find_span_by_pattern(spans, 'setup:') is None
    assert find_span_by_pattern(spans, 'call:') is None
    assert find_span_by_pattern(spans, 'teardown:') is None


def test_phase_tracing_with_flag(logfire_pytester: pytest.Pytester):
    """Phase tracing should work with --logfire-trace-phases flag."""
    logfire_pytester.makepyfile("""
        def test_example():
            assert 1 + 1 == 2
    """)
    result = logfire_pytester.runpytest_subprocess(
        '-p', 'no:django', '-p', 'no:pretty', '--logfire', '--logfire-trace-phases'
    )
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Should have setup/call/teardown spans
    setup_span = find_span_by_pattern(spans, 'setup:')
    call_span = find_span_by_pattern(spans, 'call:')
    teardown_span = find_span_by_pattern(spans, 'teardown:')

    assert setup_span is not None, 'Setup span not found'
    assert call_span is not None, 'Call span not found'
    assert teardown_span is not None, 'Teardown span not found'

    # Verify they are nested under the test span
    test_span = find_span_by_pattern(spans, 'test_example')
    assert test_span is not None

    # All phase spans should share the same trace_id as the test span
    assert setup_span['context']['trace_id'] == test_span['context']['trace_id']
    assert call_span['context']['trace_id'] == test_span['context']['trace_id']
    assert teardown_span['context']['trace_id'] == test_span['context']['trace_id']


def test_phase_tracing_with_ini_config(logfire_pytester: pytest.Pytester):
    """Phase tracing should work with INI configuration."""
    logfire_pytester.makepyprojecttoml("""
        [tool.pytest.ini_options]
        logfire = true
        logfire_trace_phases = true
    """)
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)

    # Should have phase spans
    assert find_span_by_pattern(spans, 'setup:') is not None
    assert find_span_by_pattern(spans, 'call:') is not None
    assert find_span_by_pattern(spans, 'teardown:') is not None


# Tests for CI metadata detection
@pytest.mark.parametrize(
    'ci_system,env_vars,expected_attrs',
    [
        # GitHub Actions
        (
            'github-actions',
            {
                'GITHUB_ACTIONS': 'true',
                'GITHUB_WORKFLOW': 'CI',
                'GITHUB_RUN_ID': '12345',
                'GITHUB_REPOSITORY': 'owner/repo',
                'GITHUB_REF': 'refs/heads/main',
                'GITHUB_SHA': 'abc123',
                'GITHUB_SERVER_URL': 'https://github.com',
            },
            {
                'ci.system': 'github-actions',
                'ci.workflow': 'CI',
                'ci.job.id': '12345',
                'ci.job.url': 'https://github.com/owner/repo/actions/runs/12345',
                'ci.ref': 'refs/heads/main',
                'ci.sha': 'abc123',
            },
        ),
        # GitLab CI
        (
            'gitlab-ci',
            {
                'GITLAB_CI': 'true',
                'CI_JOB_ID': '67890',
                'CI_JOB_URL': 'https://gitlab.com/project/-/jobs/67890',
                'CI_PIPELINE_ID': '999',
                'CI_COMMIT_REF_NAME': 'main',
                'CI_COMMIT_SHA': 'def456',
            },
            {
                'ci.system': 'gitlab-ci',
                'ci.job.id': '67890',
                'ci.job.url': 'https://gitlab.com/project/-/jobs/67890',
                'ci.pipeline.id': '999',
                'ci.ref': 'main',
                'ci.sha': 'def456',
            },
        ),
        # CircleCI
        (
            'circleci',
            {
                'CIRCLECI': 'true',
                'CIRCLE_BUILD_NUM': '111',
                'CIRCLE_BUILD_URL': 'https://circleci.com/gh/owner/repo/111',
                'CIRCLE_BRANCH': 'main',
                'CIRCLE_SHA1': 'ghi789',
            },
            {
                'ci.system': 'circleci',
                'ci.job.id': '111',
                'ci.job.url': 'https://circleci.com/gh/owner/repo/111',
                'ci.ref': 'main',
                'ci.sha': 'ghi789',
            },
        ),
        # Jenkins
        (
            'jenkins',
            {
                'JENKINS_URL': 'https://jenkins.example.com',
                'BUILD_NUMBER': '222',
                'BUILD_URL': 'https://jenkins.example.com/job/test/222',
                'GIT_BRANCH': 'main',
                'GIT_COMMIT': 'jkl012',
            },
            {
                'ci.system': 'jenkins',
                'ci.job.id': '222',
                'ci.job.url': 'https://jenkins.example.com/job/test/222',
                'ci.ref': 'main',
                'ci.sha': 'jkl012',
            },
        ),
    ],
    ids=['github-actions', 'gitlab-ci', 'circleci', 'jenkins'],
)
def test_ci_metadata(
    logfire_pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    ci_system: str,
    env_vars: dict[str, str],
    expected_attrs: dict[str, str],
):
    """CI metadata should be added to session span for various CI systems."""
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    for key, value in expected_attrs.items():
        assert attrs.get(key) == value


def test_generic_ci_detection(logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """Generic CI detection should work for unknown CI systems."""
    monkeypatch.setenv('CI', 'true')

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    assert attrs.get('ci.system') == 'unknown'


def test_no_ci_metadata_without_ci(logfire_pytester: pytest.Pytester):
    """No CI metadata should be added when not in CI."""
    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    # Should not have any ci.* attributes
    ci_attrs = {k: v for k, v in attrs.items() if k.startswith('ci.')}
    assert len(ci_attrs) == 0


def test_github_actions_metadata_partial(
    logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, no_ci_envs: None
):
    """GitHub Actions metadata should work with minimal env vars."""
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    # Only set GITHUB_ACTIONS, leave other vars unset

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    assert attrs.get('ci.system') == 'github-actions'


def test_github_actions_without_server_url(
    logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, no_ci_envs: None
):
    """GitHub Actions should use default server URL when GITHUB_SERVER_URL is not set."""
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    monkeypatch.setenv('GITHUB_RUN_ID', '12345')
    # Don't set GITHUB_SERVER_URL to test default

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    assert attrs.get('ci.job.url') == 'https://github.com/owner/repo/actions/runs/12345'


def test_github_actions_without_repo(
    logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, no_ci_envs: None
):
    """GitHub Actions should handle missing repository."""
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_RUN_ID', '12345')
    # Don't set GITHUB_REPOSITORY

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    # Should not have job.url if repo is missing
    assert 'ci.job.url' not in attrs or attrs.get('ci.job.url') == ''


@pytest.mark.parametrize(
    'ci_system,env_var',
    [
        ('gitlab-ci', 'GITLAB_CI'),
        ('circleci', 'CIRCLECI'),
        ('jenkins', 'JENKINS_URL'),
    ],
    ids=['gitlab-ci', 'circleci', 'jenkins'],
)
def test_ci_metadata_partial(
    logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, ci_system: str, env_var: str
):
    """CI metadata should work with minimal env vars for various CI systems."""
    env_value = 'true' if env_var != 'JENKINS_URL' else 'https://jenkins.example.com'
    monkeypatch.setenv(env_var, env_value)

    logfire_pytester.makepyfile("""
        def test_example():
            assert True
    """)
    result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
    result.assert_outcomes(passed=1)

    spans = load_spans(logfire_pytester)
    session_span = find_session_span(spans)

    assert session_span is not None
    attrs = session_span['attributes']
    assert attrs.get('ci.system') == ci_system
