---
title: "Logfire Pytest Integration: Setup Guide"
description: "Enable distributed tracing for your pytest test suite with Pydantic Logfire. Trace test sessions, individual tests, and see spans from instrumented libraries."
integration: logfire
---
# Pytest

!!! tip "Running under Pytest... 🧪"
    Only Pytest spans are send by default. Please refer to the [Testing Logfire Instrumentation](../reference/advanced/testing.md) guide for details on testing application instrumentation.

Logfire includes a built-in Pytest plugin that enables distributed tracing for your test suite. The plugin creates spans for test sessions and individual tests, allowing you to see exactly what happens during test execution.

## Installation

The pytest plugin is included with `logfire` - no additional installation required:

{{ install_logfire() }}

## Enabling the Plugin

The plugin can be enabled in several ways:

### Command Line Flag

```bash
pytest --logfire
```

### Configuration File

=== "`pytest.toml`"

    ```toml
    [pytest]
    logfire = true
    ```

=== "`pyproject.toml`"

    ```toml
    [tool.pytest]
    logfire = true
    ```

### Auto-Enable in CI

The plugin automatically enables when both:

- `CI` environment variable is set to a non-empty string
- `LOGFIRE_TOKEN` environment variable is present

This means your CI pipelines will automatically get tracing without any configuration changes.

### Explicitly Disable

To explicitly disable the plugin (useful to override auto-enable in CI):

```bash
pytest --no-logfire
```

## Configuration Options

| Option | CLI Flag | Config option | Environment variable | Default | Description |
|--------|----------|------------|---------------------|---------|-------------|
| Enable | `--logfire` | `logfire = true` | - | `false` | Enable the plugin |
| Disable | `--no-logfire` | - | - | - | Explicitly disable |
| Service Name | `--logfire-service-name` | `logfire_service_name` | `LOGFIRE_SERVICE_NAME` | `pytest` | Service name for traces |

Configuration priority: CLI > Environment Variable > INI > Default

## Trace Hierarchy

When running tests with `--logfire`, the plugin creates a hierarchical trace structure:

```
pytest: {project-name}                    (session span)
├── test_module.py::test_one              (test span)
│   └── custom span                       (your spans)
├── test_module.py::test_two              (test span)
└── test_module.py::TestClass::test_three (test span)
```

### Session Span

The session span (`pytest: {project-name}`) wraps the entire test run and includes:

| Attribute | Description |
|-----------|-------------|
| `pytest.args` | Command line arguments |
| `pytest.rootpath` | Project root path |
| `pytest.startpath` | Invocation path |
| `pytest.testscollected` | Number of tests collected |
| `pytest.testsfailed` | Number of tests failed |
| `pytest.exitstatus` | Exit code |

### Test Spans

Each test gets its own span with:

| Attribute | Description |
|-----------|-------------|
| `test.name` | Test function name |
| `test.nodeid` | Full pytest node ID (e.g., `test_file.py::test_func`) |
| `test.class` | Test class name (if applicable) |
| `test.module` | Test module name |
| `test.parameters` | Parameterized test arguments (JSON) |
| `test.outcome` | `passed`, `failed`, or `skipped` |
| `test.duration_ms` | Test duration in milliseconds |
| `code.filepath` | Path to test file |
| `code.function` | Test function name |
| `code.lineno` | Line number |

## Using with Instrumented Libraries

When running tests with `--logfire`, any instrumented library calls create spans nested under the test span. This provides end-to-end visibility into what your tests are doing.

### Example: Custom Spans in Tests

```python title="test_api.py"
def test_user_workflow(logfire_instance):
    """Test a complete user workflow."""
    with logfire_instance.span('create user'):
        # Simulate user creation
        user = {'id': 123, 'name': 'Test User'}
        assert user['name'] == 'Test User'

    with logfire_instance.span('verify user'):
        # Verify the user was created correctly
        assert user['id'] == 123
```

!!! tip "Use `logfire_instance` fixture"
    When creating spans within tests, prefer using the injected `logfire_instance` fixture instead of the global `logfire` object for fine control of which spans are send to Logfire.

Running with `pytest --logfire` produces this trace hierarchy:

```
pytest: my-project
└── test_api.py::test_user_workflow
    ├── create user
    └── verify user
```

### Example: Logging During Tests

```python skip="true" skip-reason="incomplete"
def test_operation(logfire_instance):
    logfire_instance.info("Starting operation")
    result = perform_operation()
    logfire_instance.info("Operation completed", result=result)
    assert result == expected
```

All log messages appear as spans nested under the test span.

## Application Code Spans

You need to explicitly enable sending spans from your application code during tests, since the default behavior is to only send Pytest spans. To do this, configure Logfire in your application code with `send_to_logfire=True` or `send_to_logfire='if-token-present'`:

```python title="app.py"
import logfire

logfire.configure(send_to_logfire=True)

def perform_operation():
    with logfire.span("performing operation"):
        # Simulate some work
        return 42
```

When running tests with `--logfire`, spans from `perform_operation` will appear under the test span.

## Linking to External Traces

You can link your test traces to external systems using the `TRACEPARENT` environment variable:

```bash
TRACEPARENT="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01" pytest --logfire
```

This follows the [W3C Trace Context](https://www.w3.org/TR/trace-context/) specification, allowing your test runs to be part of a larger distributed trace.

## Benefits

1. **Debugging Failed Tests**: See exactly what operations occurred before a test failure
2. **Performance Analysis**: Identify slow operations within your tests
3. **Integration Testing**: Verify that your code makes the expected calls to external services
4. **CI Visibility**: Get detailed traces from your CI pipelines automatically

## Example: Viewing in Logfire

After running your tests with `--logfire`, you can view the traces in the Logfire web UI:

1. Navigate to your project in Logfire
2. Filter by service name `pytest` (or your custom service name)
3. Explore the trace hierarchy to see:
    - Which tests passed/failed
    - How long each test took
    - What operations occurred within each test
    - Any exceptions that were raised

## Migration from conftest.py Pattern

If you were previously using a manual tracing pattern in `conftest.py`:

```python skip="true" skip-reason="incomplete"
# Old pattern - no longer needed
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item):
    with logfire.span("test: {test_name}", test_name=item.name):
        yield
```

You can remove this code and simply use `pytest --logfire` instead. The built-in plugin handles all the tracing automatically with more comprehensive attributes.
