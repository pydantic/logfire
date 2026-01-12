from types import ModuleType
from unittest import mock

import pytest
from inline_snapshot import snapshot

import logfire


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
