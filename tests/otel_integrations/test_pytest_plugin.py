"""Tests for the pytest plugin."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownLambdaType=false

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from logfire._internal.integrations import pytest as pytest_plugin


class TestAutoEnable:
    """Tests for auto-enable logic."""

    def test_should_auto_enable_with_ci_and_token(self, monkeypatch: pytest.MonkeyPatch):
        """Should auto-enable when CI=true and LOGFIRE_TOKEN is set."""
        monkeypatch.setenv('CI', 'true')
        monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')
        assert pytest_plugin._should_auto_enable() is True

    def test_should_not_auto_enable_without_ci(self, monkeypatch: pytest.MonkeyPatch):
        """Should not auto-enable without CI env var."""
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')
        assert pytest_plugin._should_auto_enable() is False

    def test_should_not_auto_enable_without_token(self, monkeypatch: pytest.MonkeyPatch):
        """Should not auto-enable without LOGFIRE_TOKEN."""
        monkeypatch.setenv('CI', 'true')
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
        assert pytest_plugin._should_auto_enable() is False

    def test_should_not_auto_enable_with_ci_false(self, monkeypatch: pytest.MonkeyPatch):
        """Should not auto-enable when CI=false."""
        monkeypatch.setenv('CI', 'false')
        monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')
        assert pytest_plugin._should_auto_enable() is False


class TestIsEnabled:
    """Tests for plugin enable/disable logic."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch):
        """Plugin should be disabled by default."""
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)

        config = mock.MagicMock()
        config.getoption.return_value = False
        config.getini.return_value = False

        assert pytest_plugin._is_enabled(config) is False

    def test_enabled_with_flag(self, monkeypatch: pytest.MonkeyPatch):
        """Plugin should be enabled with --logfire flag."""
        monkeypatch.delenv('CI', raising=False)

        config = mock.MagicMock()
        config.getoption.side_effect = lambda opt, default=None: opt == '--logfire'
        config.getini.return_value = False

        assert pytest_plugin._is_enabled(config) is True

    def test_disabled_with_no_logfire_flag(self, monkeypatch: pytest.MonkeyPatch):
        """Plugin should be disabled with --no-logfire flag even in CI."""
        monkeypatch.setenv('CI', 'true')
        monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')

        config = mock.MagicMock()
        config.getoption.side_effect = lambda opt, default=None: opt == '--no-logfire'
        config.getini.return_value = False

        assert pytest_plugin._is_enabled(config) is False

    def test_enabled_with_ini(self, monkeypatch: pytest.MonkeyPatch):
        """Plugin should be enabled with INI option."""
        monkeypatch.delenv('CI', raising=False)

        config = mock.MagicMock()
        config.getoption.return_value = False
        config.getini.side_effect = lambda opt: opt == 'logfire'

        assert pytest_plugin._is_enabled(config) is True

    def test_auto_enabled_in_ci(self, monkeypatch: pytest.MonkeyPatch):
        """Plugin should auto-enable in CI with token."""
        monkeypatch.setenv('CI', 'true')
        monkeypatch.setenv('LOGFIRE_TOKEN', 'test-token')

        config = mock.MagicMock()
        config.getoption.return_value = False
        config.getini.return_value = False

        assert pytest_plugin._is_enabled(config) is True


class TestServiceName:
    """Tests for service name configuration."""

    def test_default_service_name(self, monkeypatch: pytest.MonkeyPatch):
        """Should return default service name."""
        monkeypatch.delenv('LOGFIRE_SERVICE_NAME', raising=False)

        config = mock.MagicMock()
        config.getoption.return_value = None
        config.getini.return_value = None

        assert pytest_plugin._get_service_name(config) == 'pytest'

    def test_service_name_from_cli(self, monkeypatch: pytest.MonkeyPatch):
        """CLI option should take precedence."""
        monkeypatch.setenv('LOGFIRE_SERVICE_NAME', 'env-service')

        config = mock.MagicMock()
        config.getoption.return_value = 'cli-service'
        config.getini.return_value = 'ini-service'

        assert pytest_plugin._get_service_name(config) == 'cli-service'

    def test_service_name_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """Environment variable should be second priority."""
        monkeypatch.setenv('LOGFIRE_SERVICE_NAME', 'env-service')

        config = mock.MagicMock()
        config.getoption.return_value = None
        config.getini.return_value = 'ini-service'

        assert pytest_plugin._get_service_name(config) == 'env-service'

    def test_service_name_from_ini(self, monkeypatch: pytest.MonkeyPatch):
        """INI option should be third priority."""
        monkeypatch.delenv('LOGFIRE_SERVICE_NAME', raising=False)

        config = mock.MagicMock()
        config.getoption.return_value = None
        config.getini.return_value = 'ini-service'

        assert pytest_plugin._get_service_name(config) == 'ini-service'


pytest_plugins = ['pytester']


class TestPytestIntegration:
    """Integration tests using pytester."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        pytester.makeini("""
            [pytest]
            addopts = -p no:langsmith
        """)
        return pytester

    def test_plugin_disabled_by_default(self, logfire_pytester: pytest.Pytester):
        """Plugin should do nothing without --logfire flag."""
        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django')
        result.stdout.fnmatch_lines(['*1 passed*'])

    def test_help_shows_logfire_options(self, logfire_pytester: pytest.Pytester):
        """Help text should show Logfire options."""
        result = logfire_pytester.runpytest_subprocess('--help')
        result.stdout.fnmatch_lines(
            [
                '*logfire*',
                '*--logfire*',
            ]
        )

    def test_plugin_runs_with_flag(self, logfire_pytester: pytest.Pytester):
        """Plugin should run with --logfire flag."""
        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.stdout.fnmatch_lines(['*1 passed*'])

    def test_ini_config_enables_plugin(self, logfire_pytester: pytest.Pytester):
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


class TestSpanCapture:
    """Tests that verify spans are captured correctly with expected hierarchy and attributes."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)

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
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from captured file."""
        import json

        spans_file = pytester.path / 'spans.json'
        if not spans_file.exists():
            return []
        return json.loads(spans_file.read_text())

    def _find_span_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
        """Find span by name pattern."""
        for span in spans:
            name = span.get('name', '')
            if isinstance(name, str) and pattern in name:
                return span
        return None

    def _find_spans_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
        """Find all spans matching name pattern."""
        result: list[dict[str, Any]] = []
        for span in spans:
            name = span.get('name', '')
            if isinstance(name, str) and pattern in name:
                result.append(span)
        return result

    def test_session_span_attributes(self, logfire_pytester: pytest.Pytester):
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

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_span_by_pattern(spans, 'pytest:')
        assert session_span is not None, 'Session span not found'

        attrs = session_span['attributes']
        assert 'pytest.args' in attrs
        assert 'pytest.rootpath' in attrs
        assert 'pytest.testscollected' in attrs
        assert attrs['pytest.testscollected'] == 3
        assert 'pytest.testsfailed' in attrs
        assert attrs['pytest.testsfailed'] == 1
        assert 'pytest.exitstatus' in attrs

    def test_test_span_attributes(self, logfire_pytester: pytest.Pytester):
        """Verify test spans have correct attributes (from documentation example)."""
        logfire_pytester.makepyfile("""
            def test_passing():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        test_span = self._find_span_by_pattern(spans, 'test_passing')
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

    def test_failed_test_records_exception(self, logfire_pytester: pytest.Pytester):
        """Failed tests should record exception with traceback (from documentation example)."""
        logfire_pytester.makepyfile("""
            def test_failure():
                assert False, "intentional failure"
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(failed=1)

        spans = self._load_spans(logfire_pytester)
        test_span = self._find_span_by_pattern(spans, 'test_failure')
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

    def test_skipped_test_with_reason(self, logfire_pytester: pytest.Pytester):
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

        spans = self._load_spans(logfire_pytester)
        test_span = self._find_span_by_pattern(spans, 'test_skipped')
        assert test_span is not None, 'Test span not found'

        # Verify basic test attributes are still recorded
        attrs = test_span['attributes']
        assert attrs['test.name'] == 'test_skipped'
        assert 'test.nodeid' in attrs
        assert 'code.filepath' in attrs

    def test_parameterized_tests(self, logfire_pytester: pytest.Pytester):
        """Parameterized tests should record parameters (from documentation example)."""
        logfire_pytester.makepyfile("""
            import pytest

            @pytest.mark.parametrize("value", [1, 2, 3])
            def test_param(value):
                assert value > 0
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=3)

        spans = self._load_spans(logfire_pytester)
        param_spans = self._find_spans_by_pattern(spans, 'test_param')
        assert len(param_spans) == 3, 'Should have 3 parameterized test spans'

        for span in param_spans:
            attrs = span['attributes']
            assert attrs['test.outcome'] == 'passed'
            assert 'test.parameters' in attrs

    def test_test_spans_nested_under_session(self, logfire_pytester: pytest.Pytester):
        """Test spans should be children of session span."""
        logfire_pytester.makepyfile("""
            def test_one():
                assert True

            def test_two():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=2)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_span_by_pattern(spans, 'pytest:')
        test_spans = self._find_spans_by_pattern(spans, 'test_')

        assert session_span is not None
        assert len(test_spans) == 2

        session_span_id = session_span['context']['span_id']

        for test_span in test_spans:
            assert test_span['parent'] is not None, 'Test span should have parent'
            assert test_span['parent']['span_id'] == session_span_id, 'Test span parent should be session'

    def test_class_based_test(self, logfire_pytester: pytest.Pytester):
        """Class-based tests should include class name in attributes."""
        logfire_pytester.makepyfile("""
            class TestMyClass:
                def test_method(self):
                    assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        test_span = self._find_span_by_pattern(spans, 'test_method')
        assert test_span is not None

        attrs = test_span['attributes']
        assert attrs.get('test.class') == 'TestMyClass'
        assert 'test.module' in attrs


class TestHttpxIntegration:
    """Tests for HTTPX integration with pytest plugin (from documentation examples)."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)

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
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from captured file."""
        import json

        spans_file = pytester.path / 'spans.json'
        if not spans_file.exists():
            return []
        return json.loads(spans_file.read_text())

    def _find_span_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
        """Find span by name pattern."""
        for span in spans:
            name = span.get('name', '')
            if isinstance(name, str) and pattern in name:
                return span
        return None

    def _find_spans_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
        """Find all spans matching name pattern."""
        return [span for span in spans if isinstance(span.get('name', ''), str) and pattern in span.get('name', '')]

    def test_custom_spans_nested_under_test_span(self, logfire_pytester: pytest.Pytester):
        """Custom logfire spans during tests should be nested under test spans.

        This verifies that any spans created via logfire.span() during test execution
        are properly nested under the test span.
        """
        logfire_pytester.makepyfile("""
            import logfire

            def test_with_custom_span():
                with logfire.span("fetching data"):
                    # Simulate some work
                    result = 1 + 1
                    assert result == 2
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Find the relevant spans
        session_span = self._find_span_by_pattern(spans, 'pytest:')
        test_span = self._find_span_by_pattern(spans, 'test_with_custom_span')
        custom_span = self._find_span_by_pattern(spans, 'fetching data')

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

    def test_nested_custom_spans_hierarchy(self, logfire_pytester: pytest.Pytester):
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
            import logfire

            def test_nested_workflow():
                with logfire.span("create user"):
                    with logfire.span("validate input"):
                        # Simulate validation
                        user_data = {"name": "Test User"}
                        assert "name" in user_data

                with logfire.span("verify user"):
                    with logfire.span("check permissions"):
                        # Simulate permission check
                        has_permission = True
                        assert has_permission
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Find the relevant spans
        test_span = self._find_span_by_pattern(spans, 'test_nested_workflow')
        create_span = self._find_span_by_pattern(spans, 'create user')
        verify_span = self._find_span_by_pattern(spans, 'verify user')
        validate_span = self._find_span_by_pattern(spans, 'validate input')
        permissions_span = self._find_span_by_pattern(spans, 'check permissions')

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

    def test_logfire_info_creates_span(self, logfire_pytester: pytest.Pytester):
        """Logfire log calls during tests should create spans nested under test span.

        This tests that logfire.info() and similar calls work correctly within tests.
        """
        logfire_pytester.makepyfile("""
            import logfire

            def test_with_logging():
                logfire.info("Starting test operation")
                result = 42
                logfire.info("Operation completed", result=result)
                assert result == 42
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Find test span and log spans
        test_span = self._find_span_by_pattern(spans, 'test_with_logging')
        assert test_span is not None, 'Test span not found'

        # Find log spans
        log_spans = self._find_spans_by_pattern(spans, 'Starting test operation')
        completed_spans = self._find_spans_by_pattern(spans, 'Operation completed')

        assert len(log_spans) >= 1, 'Starting log span not found'
        assert len(completed_spans) >= 1, 'Completed log span not found'

        # Verify log spans are children of test span
        for log_span in log_spans + completed_spans:
            assert log_span['parent'] is not None
            assert log_span['parent']['span_id'] == test_span['context']['span_id']


class TestTraceparentPropagation:
    """Tests for TRACEPARENT environment variable support."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)

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
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from captured file."""
        import json

        spans_file = pytester.path / 'spans.json'
        if not spans_file.exists():
            return []
        return json.loads(spans_file.read_text())

    def test_traceparent_env_var_support(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """TRACEPARENT environment variable should link traces to external systems.

        From documentation: The traceparent header is automatically added to outgoing
        requests, allowing correlation with downstream services.
        """
        # Set a known TRACEPARENT value (W3C trace context format)
        # Format: version-trace_id-parent_id-flags
        # Note: The pytest plugin should attach to this trace context
        monkeypatch.setenv('TRACEPARENT', '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01')

        logfire_pytester.makepyfile("""
            def test_with_traceparent():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        # The test should pass - TRACEPARENT handling is internal to the plugin
        # This test verifies the plugin doesn't break when TRACEPARENT is set


class TestLogfireFixture:
    """Tests for the logfire fixture."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
        monkeypatch.delenv('TRACEPARENT', raising=False)
        monkeypatch.delenv('TRACESTATE', raising=False)

        # Create a conftest that captures spans to a JSON file
        pytester.makeconftest('''
import json
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from logfire._internal.exporters.test import TestExporter

_exporter = TestExporter()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Add our test exporter AFTER logfire plugin has configured the tracer."""
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from captured file."""
        import json

        spans_file = pytester.path / 'spans.json'
        if not spans_file.exists():
            return []
        return json.loads(spans_file.read_text())

    def _find_span_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
        """Find span by name pattern."""
        for span in spans:
            name = span.get('name', '')
            if isinstance(name, str) and pattern in name:
                return span
        return None

    def test_logfire_fixture_works_without_plugin_enabled(self, logfire_pytester: pytest.Pytester):
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

    def test_logfire_fixture_returns_instance_when_enabled(self, logfire_pytester: pytest.Pytester):
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

    def test_logfire_fixture_can_create_spans(self, logfire_pytester: pytest.Pytester):
        """The logfire_instance fixture should be able to create spans that nest under test spans."""
        logfire_pytester.makepyfile("""
            def test_using_logfire_fixture(logfire_instance):
                with logfire_instance.span("custom span from fixture"):
                    assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Find the test span and custom span
        test_span = self._find_span_by_pattern(spans, 'test_using_logfire_fixture')
        custom_span = self._find_span_by_pattern(spans, 'custom span from fixture')

        assert test_span is not None, 'Test span not found'
        assert custom_span is not None, 'Custom span not found'

        # Verify the custom span is nested under the test span
        assert custom_span['parent'] is not None
        assert custom_span['parent']['span_id'] == test_span['context']['span_id']

    def test_logfire_fixture_in_test_fixture(self, logfire_pytester: pytest.Pytester):
        """The logfire_instance fixture should work when used in user fixtures."""
        # First make the span capture conftest
        logfire_pytester.makeconftest('''
import json
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from logfire._internal.exporters.test import TestExporter

_exporter = TestExporter()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Add our test exporter AFTER logfire plugin has configured the tracer."""
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Write captured spans to file after logfire plugin closes session span."""
    # Yield first to let logfire close the session span
    yield
    # Now capture all spans including the session span
    spans_data = _exporter.exported_spans_as_dict()
    with open("spans.json", "w") as f:
        json.dump(spans_data, f, indent=2)


@pytest.fixture
def my_client(logfire_instance):
    """A fixture that uses the logfire_instance fixture."""
    with logfire_instance.span("setting up client"):
        client = {"url": "https://api.example.com"}
    return client
''')
        logfire_pytester.makepyfile("""
            def test_with_client_fixture(my_client):
                assert my_client["url"] == "https://api.example.com"
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Find the test span and setup span
        test_span = self._find_span_by_pattern(spans, 'test_with_client_fixture')
        setup_span = self._find_span_by_pattern(spans, 'setting up client')

        assert test_span is not None, 'Test span not found'
        assert setup_span is not None, 'Setup span not found'

        # Note: The setup span will be a sibling of the test span (both under session)
        # because fixture setup happens before test execution in pytest
        # We just verify both spans exist
        assert setup_span is not None


class TestPhaseTracing:
    """Tests for --logfire-trace-phases feature."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
        monkeypatch.delenv('TRACEPARENT', raising=False)
        monkeypatch.delenv('TRACESTATE', raising=False)
        monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
        monkeypatch.delenv('GITLAB_CI', raising=False)
        monkeypatch.delenv('CIRCLECI', raising=False)
        monkeypatch.delenv('JENKINS_URL', raising=False)

        # Create a conftest that captures spans to a JSON file
        pytester.makeconftest('''
import json
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from logfire._internal.exporters.test import TestExporter

_exporter = TestExporter()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Add our test exporter AFTER logfire plugin has configured the tracer."""
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from the captured JSON file."""
        import json

        spans_file = pytester.path / 'spans.json'
        return json.loads(spans_file.read_text())

    def _find_span_by_pattern(self, spans: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
        """Find a span by name pattern."""
        for span in spans:
            if pattern in span['name']:
                return span
        return None

    def test_phase_tracing_disabled_by_default(self, logfire_pytester: pytest.Pytester):
        """Phase tracing should be disabled by default."""
        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Should not have setup/call/teardown spans
        assert self._find_span_by_pattern(spans, 'setup:') is None
        assert self._find_span_by_pattern(spans, 'call:') is None
        assert self._find_span_by_pattern(spans, 'teardown:') is None

    def test_phase_tracing_with_flag(self, logfire_pytester: pytest.Pytester):
        """Phase tracing should work with --logfire-trace-phases flag."""
        logfire_pytester.makepyfile("""
            def test_example():
                assert 1 + 1 == 2
        """)
        result = logfire_pytester.runpytest_subprocess(
            '-p', 'no:django', '-p', 'no:pretty', '--logfire', '--logfire-trace-phases'
        )
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)

        # Should have setup/call/teardown spans
        setup_span = self._find_span_by_pattern(spans, 'setup:')
        call_span = self._find_span_by_pattern(spans, 'call:')
        teardown_span = self._find_span_by_pattern(spans, 'teardown:')

        assert setup_span is not None, 'Setup span not found'
        assert call_span is not None, 'Call span not found'
        assert teardown_span is not None, 'Teardown span not found'

        # Verify they are nested under the test span
        test_span = self._find_span_by_pattern(spans, 'test_example')
        assert test_span is not None

        # All phase spans should share the same trace_id as the test span
        assert setup_span['context']['trace_id'] == test_span['context']['trace_id']
        assert call_span['context']['trace_id'] == test_span['context']['trace_id']
        assert teardown_span['context']['trace_id'] == test_span['context']['trace_id']

    def test_phase_tracing_with_ini_config(self, logfire_pytester: pytest.Pytester):
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

        spans = self._load_spans(logfire_pytester)

        # Should have phase spans
        assert self._find_span_by_pattern(spans, 'setup:') is not None
        assert self._find_span_by_pattern(spans, 'call:') is not None
        assert self._find_span_by_pattern(spans, 'teardown:') is not None


class TestCIMetadata:
    """Tests for CI metadata detection."""

    @pytest.fixture
    def logfire_pytester(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
        """Pytester pre-configured for logfire plugin testing with span capture."""
        monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
        monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
        monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
        monkeypatch.delenv('TRACEPARENT', raising=False)
        monkeypatch.delenv('TRACESTATE', raising=False)
        monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
        monkeypatch.delenv('GITLAB_CI', raising=False)
        monkeypatch.delenv('CIRCLECI', raising=False)
        monkeypatch.delenv('JENKINS_URL', raising=False)

        # Create a conftest that captures spans to a JSON file
        pytester.makeconftest('''
import json
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from logfire._internal.exporters.test import TestExporter

_exporter = TestExporter()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Add our test exporter AFTER logfire plugin has configured the tracer."""
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    # Add our exporter to capture spans
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(_exporter))


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

    def _load_spans(self, pytester: pytest.Pytester) -> list[dict[str, Any]]:
        """Load spans from the captured JSON file."""
        import json

        spans_file = pytester.path / 'spans.json'
        return json.loads(spans_file.read_text())

    def _find_session_span(self, spans: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find the session span."""
        for span in spans:
            if 'pytest:' in span['name']:
                return span
        return None

    def test_github_actions_metadata(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """GitHub Actions metadata should be added to session span."""
        monkeypatch.setenv('GITHUB_ACTIONS', 'true')
        monkeypatch.setenv('GITHUB_WORKFLOW', 'CI')
        monkeypatch.setenv('GITHUB_RUN_ID', '12345')
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
        monkeypatch.setenv('GITHUB_SHA', 'abc123')
        monkeypatch.setenv('GITHUB_SERVER_URL', 'https://github.com')

        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_session_span(spans)

        assert session_span is not None
        attrs = session_span['attributes']
        assert attrs.get('ci.system') == 'github-actions'
        assert attrs.get('ci.workflow') == 'CI'
        assert attrs.get('ci.job.id') == '12345'
        assert attrs.get('ci.job.url') == 'https://github.com/owner/repo/actions/runs/12345'
        assert attrs.get('ci.ref') == 'refs/heads/main'
        assert attrs.get('ci.sha') == 'abc123'

    def test_gitlab_ci_metadata(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """GitLab CI metadata should be added to session span."""
        monkeypatch.setenv('GITLAB_CI', 'true')
        monkeypatch.setenv('CI_JOB_ID', '67890')
        monkeypatch.setenv('CI_JOB_URL', 'https://gitlab.com/project/-/jobs/67890')
        monkeypatch.setenv('CI_PIPELINE_ID', '999')
        monkeypatch.setenv('CI_COMMIT_REF_NAME', 'main')
        monkeypatch.setenv('CI_COMMIT_SHA', 'def456')

        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_session_span(spans)

        assert session_span is not None
        attrs = session_span['attributes']
        assert attrs.get('ci.system') == 'gitlab-ci'
        assert attrs.get('ci.job.id') == '67890'
        assert attrs.get('ci.job.url') == 'https://gitlab.com/project/-/jobs/67890'
        assert attrs.get('ci.pipeline.id') == '999'
        assert attrs.get('ci.ref') == 'main'
        assert attrs.get('ci.sha') == 'def456'

    def test_circleci_metadata(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """CircleCI metadata should be added to session span."""
        monkeypatch.setenv('CIRCLECI', 'true')
        monkeypatch.setenv('CIRCLE_BUILD_NUM', '111')
        monkeypatch.setenv('CIRCLE_BUILD_URL', 'https://circleci.com/gh/owner/repo/111')
        monkeypatch.setenv('CIRCLE_BRANCH', 'main')
        monkeypatch.setenv('CIRCLE_SHA1', 'ghi789')

        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_session_span(spans)

        assert session_span is not None
        attrs = session_span['attributes']
        assert attrs.get('ci.system') == 'circleci'
        assert attrs.get('ci.job.id') == '111'
        assert attrs.get('ci.job.url') == 'https://circleci.com/gh/owner/repo/111'
        assert attrs.get('ci.ref') == 'main'
        assert attrs.get('ci.sha') == 'ghi789'

    def test_jenkins_metadata(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """Jenkins metadata should be added to session span."""
        monkeypatch.setenv('JENKINS_URL', 'https://jenkins.example.com')
        monkeypatch.setenv('BUILD_NUMBER', '222')
        monkeypatch.setenv('BUILD_URL', 'https://jenkins.example.com/job/test/222')
        monkeypatch.setenv('GIT_BRANCH', 'main')
        monkeypatch.setenv('GIT_COMMIT', 'jkl012')

        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_session_span(spans)

        assert session_span is not None
        attrs = session_span['attributes']
        assert attrs.get('ci.system') == 'jenkins'
        assert attrs.get('ci.job.id') == '222'
        assert attrs.get('ci.job.url') == 'https://jenkins.example.com/job/test/222'
        assert attrs.get('ci.ref') == 'main'
        assert attrs.get('ci.sha') == 'jkl012'

    def test_generic_ci_detection(self, logfire_pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """Generic CI detection should work for unknown CI systems."""
        monkeypatch.setenv('CI', 'true')

        logfire_pytester.makepyfile("""
            def test_example():
                assert True
        """)
        result = logfire_pytester.runpytest_subprocess('-p', 'no:django', '-p', 'no:pretty', '--logfire')
        result.assert_outcomes(passed=1)

        spans = self._load_spans(logfire_pytester)
        session_span = self._find_session_span(spans)

        assert session_span is not None
        attrs = session_span['attributes']
        assert attrs.get('ci.system') == 'unknown'
