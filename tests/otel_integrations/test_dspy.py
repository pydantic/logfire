from types import ModuleType
from unittest import mock

import pytest
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter


def test_missing_openinference_dependency() -> None:
    with mock.patch.dict('sys.modules', {'openinference.instrumentation.dspy': None}):
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_dspy()
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_dspy()` method requires the `openinference-instrumentation-dspy` package.
You can install this with:
    pip install 'logfire[dspy]'\
""")


def test_instrument_dspy_calls_instrumentor() -> None:
    instrumentor = mock.Mock()
    module = ModuleType('openinference.instrumentation.dspy')
    module.DSPyInstrumentor = mock.Mock(return_value=instrumentor)  # type: ignore[attr-defined]

    with (
        mock.patch('logfire._internal.integrations.dspy.util.find_spec', return_value=object()),
        mock.patch('logfire._internal.integrations.dspy.import_module', return_value=module),
    ):
        logfire.instrument_dspy()

    instrumentor.instrument.assert_called_once()


def test_instrument_dspy_exports_span(exporter: TestExporter) -> None:
    class FakeInstrumentor:
        def instrument(self, tracer_provider, **kwargs) -> None:
            tracer = tracer_provider.get_tracer('openinference.instrumentation.dspy')
            with tracer.start_as_current_span('dspy.predict') as span:
                span.set_attribute('dspy.test', True)

    module = ModuleType('openinference.instrumentation.dspy')
    module.DSPyInstrumentor = FakeInstrumentor  # type: ignore[attr-defined]

    with (
        mock.patch('logfire._internal.integrations.dspy.util.find_spec', return_value=object()),
        mock.patch('logfire._internal.integrations.dspy.import_module', return_value=module),
    ):
        logfire.instrument_dspy()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'dspy.predict',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {'logfire.span_type': 'span', 'logfire.msg': 'dspy.predict', 'dspy.test': True},
            }
        ]
    )
