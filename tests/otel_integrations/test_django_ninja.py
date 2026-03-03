import pytest
from django.http import HttpResponse
from django.test import Client
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter
from tests.otel_integrations.django_test_project.django_test_app.views import ninja_api


@pytest.fixture(autouse=True)
def _restore_ninja_api():  # pyright: ignore[reportUnusedFunction]
    """Restore the original on_exception method after each test."""
    from ninja import NinjaAPI

    original = NinjaAPI.on_exception
    yield
    NinjaAPI.on_exception = original


def test_ninja_good_route(client: Client, exporter: TestExporter):
    logfire.instrument_django()
    response: HttpResponse = client.get('/ninja/good/')  # type: ignore
    assert response.status_code == 200

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    # No exception events for successful requests
    assert 'events' not in spans[0] or spans[0].get('events') == []


def test_ninja_error_route_without_instrumentation(client: Client, exporter: TestExporter):
    """Without instrument_ninja, handled exceptions are NOT recorded on spans."""
    logfire.instrument_django(instrument_ninja=False)
    response: HttpResponse = client.get('/ninja/error/')  # type: ignore
    assert response.status_code == 400

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    # No exception events — Django Ninja handled the exception before OTel could see it
    assert spans[0].get('events') is None or spans[0].get('events') == []


def test_ninja_error_route_with_instrumentation(client: Client, exporter: TestExporter):
    """With instrument_ninja=True (default), handled exceptions ARE recorded on spans."""
    logfire.instrument_django()
    response: HttpResponse = client.get('/ninja/error/')  # type: ignore
    assert response.status_code == 400

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1

    # Verify the exception was recorded on the span
    events = spans[0].get('events', [])
    exception_events = [e for e in events if e['name'] == 'exception']
    assert len(exception_events) == 1
    assert exception_events[0]['attributes']['exception.type'] == 'ninja.errors.HttpError'
    assert exception_events[0]['attributes']['exception.message'] == 'ninja error'
    assert exception_events[0]['attributes']['exception.escaped'] == 'False'


def test_ninja_unhandled_error_with_instrumentation(client: Client, exporter: TestExporter):
    """Unhandled exceptions (RuntimeError) are also recorded on spans."""
    logfire.instrument_django()
    client.raise_request_exception = False
    response: HttpResponse = client.get('/ninja/unhandled/')  # type: ignore
    assert response.status_code == 500

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1

    events = spans[0].get('events', [])
    exception_events = [e for e in events if e['name'] == 'exception']
    # At least one exception event should be recorded (could be 2: our hook + OTel middleware)
    assert len(exception_events) >= 1
    assert any(e['attributes']['exception.type'] == 'RuntimeError' for e in exception_events)
    assert any(e['attributes']['exception.message'] == 'unhandled ninja error' for e in exception_events)
    # Our hook records escaped=True because Django Ninja re-raises unhandled exceptions
    our_events = [
        e
        for e in exception_events
        if e['attributes']['exception.type'] == 'RuntimeError' and e['attributes'].get('exception.escaped') == 'True'
    ]
    assert len(our_events) >= 1


def test_double_instrumentation(client: Client, exporter: TestExporter):
    """Calling instrument_django twice should not double-wrap on_exception."""
    logfire.instrument_django()
    logfire.instrument_django()
    response: HttpResponse = client.get('/ninja/error/')  # type: ignore
    assert response.status_code == 400

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    events = spans[0].get('events', [])
    exception_events = [e for e in events if e['name'] == 'exception']
    # Should only record the exception once, not twice
    assert len(exception_events) == 1


def test_ninja_error_with_head_sample_rate_zero(client: Client, exporter: TestExporter):
    """When head_sample_rate=0, spans are not recording and exceptions should not be recorded."""
    from logfire.sampling import SamplingOptions

    logfire.configure(sampling=SamplingOptions(head=0.0))
    logfire.instrument_django()
    response: HttpResponse = client.get('/ninja/error/')  # type: ignore
    assert response.status_code == 400

    # No spans should be exported when sampling rate is 0
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 0


def test_ninja_unhandled_error_with_head_sample_rate_zero(client: Client, exporter: TestExporter):
    """When head_sample_rate=0, unhandled exceptions should still propagate correctly."""
    from logfire.sampling import SamplingOptions

    logfire.configure(sampling=SamplingOptions(head=0.0))
    logfire.instrument_django()
    client.raise_request_exception = False
    response: HttpResponse = client.get('/ninja/unhandled/')  # type: ignore
    assert response.status_code == 500

    # No spans should be exported when sampling rate is 0
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 0
