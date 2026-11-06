"""`logfire.configure(fleet=...)`: the calls the SDK makes into the Fleet client, with a fake client."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator, Sequence
from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, Sampler

import logfire
from logfire._internal import fleet as fleet_module
from logfire._internal.config import GLOBAL_CONFIG, LogfireConfig
from logfire._internal.exporters.dynamic_batch import DynamicBatchSpanProcessor
from logfire.fleet import FleetOptions, LogfireFleetWarning

from .test_configure import get_metric_readers, get_span_processors, wait_for_check_token_thread


class Wrapped(SpanExporter):
    """What the fake client puts around an exporter, named for the call that made it."""

    def __init__(self, call: str, exporter: Any) -> None:
        self.call = call
        self.exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:  # pragma: no cover
        return self.exporter.export(spans)


STARTED: list[dict[str, Any]] = []
"""The providers each `start` got, across clients."""


class FakeFleet:
    def __init__(self, calls: list[Any]) -> None:
        self.calls = calls
        self.started: list[dict[str, Any]] = STARTED
        self.resource_attributes = {'service.instance.id': 'fleet-uid'}

    def head_sampler(self, sampler: Sampler | None) -> Sampler:
        self.calls.append(('head_sampler', sampler))
        return ALWAYS_ON

    def redacting_spans(self, exporter: Any) -> Any:
        return Wrapped('redacting_spans', exporter)

    def spans(self, exporter: Any) -> Any:
        return Wrapped('spans', exporter)

    def logs(self, exporter: Any) -> Any:
        return Wrapped('logs', exporter)

    def metrics(self, exporter: MetricExporter) -> Any:
        self.calls.append(('metrics', exporter))
        return exporter

    def start(self, resource: Any, **providers: Any) -> None:
        self.calls.append(('start', resource.attributes['service.instance.id'], sorted(providers)))
        self.started.append(providers)


@pytest.fixture
def fleet_client() -> Iterator[tuple[list[Any], list[dict[str, Any]]]]:
    """A fake `logfire_fleet_otel`: the calls made into it, and the options `logfire_fleet` got."""
    calls: list[Any] = []
    given: list[dict[str, Any]] = []
    module = types.ModuleType('logfire_fleet_otel')

    def logfire_fleet(**options: Any) -> FakeFleet:
        given.append(options)
        return FakeFleet(calls)

    module.LOGFIRE_FLEET_CONTRACT = 1  # type: ignore[attr-defined]
    module.logfire_fleet = logfire_fleet  # type: ignore[attr-defined]
    STARTED.clear()
    with patch.dict(sys.modules, {'logfire_fleet_otel': module}), patch.object(fleet_module, '_joined_with', []):
        yield calls, given


def _chain(exporter: Any) -> list[str]:
    names: list[str] = []
    while exporter is not None:
        names.append(exporter.call if isinstance(exporter, Wrapped) else type(exporter).__name__)
        exporter = exporter.exporter if isinstance(exporter, Wrapped) else getattr(exporter, 'wrapped_exporter', None)
    return names


def test_fleet_puts_the_policy_where_it_acts(
    fleet_client: tuple[list[Any], list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, given = fleet_client
    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', lambda *args: None)  # type: ignore
    logfire.configure(
        send_to_logfire=True,
        token='pylf_v1_us_token',
        console=False,
        fleet=FleetOptions(endpoint='https://fleet.example.com/v1/opamp', heartbeat_interval=5),
    )
    wait_for_check_token_thread()

    assert given == [
        {
            'endpoint': 'https://fleet.example.com/v1/opamp',
            'headers': None,
            'state_dir': None,
            'heartbeat_interval': 5,
        }
    ]
    # The head sampler the SDK built (none: every trace) goes in, the client's comes out.
    assert calls[0] == ('head_sampler', None)
    # Metrics: the exporter to Logfire, before its reader.
    assert calls[1][0] == 'metrics'
    # Started last, with the instance ID in the resource and every provider.
    assert calls[-1] == ('start', 'fleet-uid', ['logger_provider', 'meter_provider', 'tracer_provider'])

    [processor] = [p for p in get_span_processors() if isinstance(p, DynamicBatchSpanProcessor)]
    exporter = processor.span_exporter
    # The gate above the retries, redaction under them.
    assert _chain(exporter) == [
        'RemovePendingSpansExporter',
        'spans',
        'RetryFewerSpansSpanExporter',
        'redacting_spans',
        'QuietSpanExporter',
        'BodySizeCheckingOTLPSpanExporter',
    ]
    assert len(list(get_metric_readers())) == 1


def test_fleet_from_the_environment(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    calls, given = fleet_client
    with patch.dict('os.environ', {'LOGFIRE_FLEET': 'true', 'OTEL_OPAMP_ENDPOINT': 'https://fleet.example.com'}):
        logfire.configure(send_to_logfire=False, console=False, metrics=False)
    assert given == [{'endpoint': None, 'headers': None, 'state_dir': None, 'heartbeat_interval': None}]
    assert calls[-1][0] == 'start'


def test_no_fleet_by_default(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    calls, given = fleet_client
    with patch.dict('os.environ', {'LOGFIRE_FLEET': 'false'}):
        logfire.configure(send_to_logfire=False, console=False, metrics=False)
    assert calls == given == []


def test_fleet_without_the_extra_runs_unmanaged() -> None:
    with patch.dict(sys.modules, {'logfire_fleet_otel': None}):
        with pytest.warns(LogfireFleetWarning, match=r'needs the `fleet` extra, on Python 3.11 or later') as record:
            logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=True)
    assert len([w for w in record if issubclass(w.category, LogfireFleetWarning)]) == 1
    with logfire.span('still sent'):
        pass


def test_fleet_with_another_contract_runs_unmanaged(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    calls, given = fleet_client
    sys.modules['logfire_fleet_otel'].LOGFIRE_FLEET_CONTRACT = 2  # type: ignore[attr-defined]
    with pytest.warns(LogfireFleetWarning, match='speaks contract 2, not 1') as record:
        logfire.configure(
            send_to_logfire=False, console=False, metrics=False, fleet=FleetOptions(endpoint='https://x.example')
        )
    assert len([w for w in record if issubclass(w.category, LogfireFleetWarning)]) == 1
    assert calls == given == []


def test_fleet_without_an_endpoint_runs_unmanaged(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    calls, given = fleet_client
    with patch.dict('os.environ', {'OTEL_OPAMP_ENDPOINT': ''}):
        with pytest.warns(LogfireFleetWarning, match='no Fleet endpoint is set') as record:
            logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=True)
        assert len([w for w in record if issubclass(w.category, LogfireFleetWarning)]) == 1
    assert calls == given == []


def test_fleet_switched_off_by_its_own_variable_says_nothing(
    fleet_client: tuple[list[Any], list[dict[str, Any]]],
) -> None:
    """`OTEL_OPAMP_DISABLED`: the client turns itself off (it returns None), with no endpoint warning."""
    calls, given = fleet_client
    sys.modules['logfire_fleet_otel'].logfire_fleet = lambda **_: None  # type: ignore[attr-defined]
    with patch.dict('os.environ', {'OTEL_OPAMP_ENDPOINT': '', 'OTEL_OPAMP_DISABLED': 'true'}):
        logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=True)
    assert calls == given == []


def test_fleet_without_a_client_that_imports_runs_unmanaged(
    fleet_client: tuple[list[Any], list[dict[str, Any]]],
) -> None:
    """An installed client that fails on import (not with ImportError) doesn't break `configure()`."""

    real_import = __import__

    def broken(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'logfire_fleet_otel':
            raise RuntimeError('broken native core')
        return real_import(name, *args, **kwargs)

    with patch('builtins.__import__', broken):
        with pytest.warns(LogfireFleetWarning, match='could not be imported: RuntimeError') as record:
            logfire.configure(
                send_to_logfire=False, console=False, metrics=False, fleet=FleetOptions(endpoint='https://x.example')
            )
    assert len([w for w in record if issubclass(w.category, LogfireFleetWarning)]) == 1
    with logfire.span('still sent'):
        pass


def test_fleet_gets_the_providers_the_console_and_a_later_configure_write_to(
    fleet_client: tuple[list[Any], list[dict[str, Any]]],
) -> None:
    """The console and other exporters are governed by the client from the providers it is handed (the
    client's own tests cover that): here, that it gets the providers they are on, again after a second
    `configure()`."""
    calls, _ = fleet_client
    options = FleetOptions(endpoint='https://fleet.example.com/v1/opamp')
    logfire.configure(send_to_logfire=False, metrics=False, fleet=options)
    first = GLOBAL_CONFIG.get_tracer_provider().provider
    assert STARTED[-1]['tracer_provider'] is first
    assert any(type(p).__name__ == 'SimpleSpanProcessor' for p in get_span_processors())  # the console

    logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=options)
    second = GLOBAL_CONFIG.get_tracer_provider().provider
    assert second is not first
    assert STARTED[-1]['tracer_provider'] is second
    assert [c[0] for c in calls].count('start') == 2


def test_fleet_options_reach_child_processes(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    """The config handed to process pool workers carries the Fleet options, and a worker joins with them."""
    import pickle

    from logfire._internal.integrations.executors import deserialize_config, serialize_config

    _, given = fleet_client
    options = FleetOptions(endpoint='https://fleet.example.com/v1/opamp', heartbeat_interval=5)
    logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=options)
    serialized = pickle.loads(pickle.dumps(serialize_config()))
    assert serialized['fleet'] == {
        'endpoint': 'https://fleet.example.com/v1/opamp',
        'headers': None,
        'state_dir': None,
        'heartbeat_interval': 5,
    }

    GLOBAL_CONFIG._initialized = False  # type: ignore  # as in a fresh worker
    deserialize_config(serialized)
    assert GLOBAL_CONFIG.fleet == options
    assert given[-1] == serialized['fleet']


def test_fleet_switched_off_in_code_stays_off_in_child_processes(
    fleet_client: tuple[list[Any], list[dict[str, Any]]],
) -> None:
    """`fleet=False` wins over `LOGFIRE_FLEET` in process pool workers too, which configure from the parent's config."""
    from logfire._internal.integrations.executors import deserialize_config, serialize_config

    calls, given = fleet_client
    with patch.dict('os.environ', {'LOGFIRE_FLEET': 'true', 'OTEL_OPAMP_ENDPOINT': 'https://fleet.example.com'}):
        logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=False)
        serialized = serialize_config()
        GLOBAL_CONFIG._initialized = False  # type: ignore  # as in a fresh worker
        deserialize_config(serialized)
    assert GLOBAL_CONFIG.fleet is False
    assert calls == given == []


def test_fleet_joined_once_warns_about_other_options(fleet_client: tuple[list[Any], list[dict[str, Any]]]) -> None:
    """A `local` configuration with other `FleetOptions` is governed by the connection the process already has."""
    logfire.configure(
        send_to_logfire=False, console=False, metrics=False, fleet=FleetOptions(endpoint='https://a.example')
    )
    with pytest.warns(LogfireFleetWarning, match='already joined Logfire Fleet with other `FleetOptions`') as record:
        logfire.configure(
            local=True,
            send_to_logfire=False,
            console=False,
            metrics=False,
            fleet=FleetOptions(endpoint='https://b.example'),
        )
    assert len([w for w in record if issubclass(w.category, LogfireFleetWarning)]) == 1
    # The same options again say nothing.
    logfire.configure(
        send_to_logfire=False, console=False, metrics=False, fleet=FleetOptions(endpoint='https://a.example')
    )


def test_fleet_joined_once_governs_a_later_configure_without_an_endpoint(
    fleet_client: tuple[list[Any], list[dict[str, Any]]],
) -> None:
    """`fleet=True` with no endpoint variable after joining in code: governed by that connection, not unmanaged."""
    calls, _ = fleet_client
    logfire.configure(
        send_to_logfire=False, console=False, metrics=False, fleet=FleetOptions(endpoint='https://a.example')
    )
    with patch.dict('os.environ', {'OTEL_OPAMP_ENDPOINT': ''}):
        with pytest.warns(LogfireFleetWarning, match='already joined Logfire Fleet') as record:
            logfire.configure(send_to_logfire=False, console=False, metrics=False, fleet=True)
    assert not [w for w in record if 'no Fleet endpoint' in str(w.message)]
    assert [c[0] for c in calls].count('start') == 2
