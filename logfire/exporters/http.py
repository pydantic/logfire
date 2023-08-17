import gzip
import json
import zlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from io import BytesIO
from time import sleep
from typing import Any

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter, _expo, _logger
from opentelemetry.sdk.trace import Event, ReadableSpan, Resource
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Link, Status
from opentelemetry.trace.span import SpanContext, TraceState
from opentelemetry.util.types import Attributes


class HttpJsonSpanExporter(OTLPSpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        # After the call to Shutdown subsequent calls to Export are
        # not allowed and should return a Failure result.
        if self._shutdown:
            _logger.warning('Exporter already shutdown, ignoring batch')
            return SpanExportResult.FAILURE

        serialized_data = json.dumps(encode_spans(spans))

        for delay in _expo(max_value=self._MAX_RETRY_TIMEOUT):
            if delay == self._MAX_RETRY_TIMEOUT:
                return SpanExportResult.FAILURE

            resp = self._export(serialized_data)
            # pylint: disable=no-else-return
            if resp.status_code in (200, 202):
                return SpanExportResult.SUCCESS
            elif self._retryable(resp):
                _logger.warning(
                    'Transient error %s encountered while exporting span batch, retrying in %ss.',
                    resp.reason,
                    delay,
                )
                sleep(delay)
                continue
            else:
                _logger.error(
                    'Failed to export batch code: %s, reason: %s',
                    resp.status_code,
                    resp.text,
                )
                return SpanExportResult.FAILURE
        return SpanExportResult.FAILURE

    def _export(self, serialized_data: str):
        data = serialized_data
        if self._compression == Compression.Gzip:
            gzip_data = BytesIO()
            with gzip.GzipFile(fileobj=gzip_data, mode='w') as gzip_stream:
                gzip_stream.write(serialized_data)
            data = gzip_data.getvalue()
        elif self._compression == Compression.Deflate:
            data = zlib.compress(bytes(serialized_data))

        return self._session.post(
            url=self._endpoint,
            data=data,
            verify=self._certificate_file,
            timeout=self._timeout,
            headers={'Content-Type': 'application/json'},
        )


def encode_spans(readable_spans: Sequence[ReadableSpan]) -> dict[str, Any]:
    sdk_resource_spans = defaultdict(lambda: defaultdict(list))

    for sdk_span in readable_spans:
        sdk_resource = sdk_span.resource
        sdk_instrumentation = sdk_span.instrumentation_scope or None
        pb2_span = _encode_span(sdk_span)

        sdk_resource_spans[sdk_resource][sdk_instrumentation].append(pb2_span)

    encoded_resource_spans = []

    for sdk_resource, sdk_instrumentations in sdk_resource_spans.items():
        scope_spans = []
        for sdk_instrumentation, encoded_spans in sdk_instrumentations.items():
            scope_spans.append(
                _dict_not_none(
                    scope=(_encode_instrumentation_scope(sdk_instrumentation)),
                    spans=encoded_spans,
                )
            )
        encoded_resource_spans.append(
            _dict_not_none(
                resource=_encode_resource(sdk_resource),
                scopeSpans=scope_spans,
            )
        )

    return dict(resource_spans=encoded_resource_spans)


def _encode_span(sdk_span: ReadableSpan) -> dict[str, Any]:
    span_context = sdk_span.get_span_context()
    return _dict_not_none(
        traceId=_encode_trace_id(span_context.trace_id),
        spanId=_encode_span_id(span_context.span_id),
        traceState=_encode_trace_state(span_context.trace_state),
        parentSpanId=_encode_parent_id(sdk_span.parent),
        name=sdk_span.name,
        kind=sdk_span.kind.value,
        startTimeUnixNano=sdk_span.start_time,
        endTimeUnixNano=sdk_span.end_time,
        attributes=_encode_attributes(sdk_span.attributes),
        events=_encode_events(sdk_span.events),
        links=_encode_links(sdk_span.links),
        status=_encode_status(sdk_span.status),
        droppedAttributesCount=sdk_span.dropped_attributes,
        # droppedEventsCount=sdk_span.dropped_events,
        # droppedLinksCount=sdk_span.dropped_links,
    )


def _encode_instrumentation_scope(
    instrumentation_scope: InstrumentationScope | None,
) -> dict[str, Any]:
    if instrumentation_scope is None:
        return {}
    return _dict_not_none(
        name=instrumentation_scope.name,
        version=instrumentation_scope.version,
    )


def _encode_resource(resource: Resource) -> dict[str, Any]:
    return _dict_not_none(attributes=_encode_attributes(resource.attributes))


def _encode_trace_id(trace_id: int) -> str:
    # See opentelemetry.exporter.otlp.proto.common._internal._encode_trace_id
    return trace_id.to_bytes(length=16, byteorder='big', signed=False).hex()


def _encode_span_id(span_id: int) -> str:
    # See opentelemetry.exporter.otlp.proto.common._internal._encode_span_id
    return span_id.to_bytes(length=8, byteorder='big', signed=False).hex()


def _encode_trace_state(trace_state: TraceState | None) -> str | None:
    # See opentelemetry.exporter.otlp.proto.common._internal.trace_encoder._encode_trace_state
    if trace_state is None:
        return None
    else:
        return ','.join([f'{key}={value}' for key, value in (trace_state.items())])


def _encode_parent_id(parent: SpanContext | None) -> str | None:
    # See opentelemetry.exporter.otlp.proto.common._internal._encode_parent_id
    if parent is None or parent.span_id is None:
        return None
    else:
        return _encode_span_id(parent.span_id)


def _encode_attributes(attributes: Attributes) -> list[dict[str, Any]] | None:
    if not attributes:
        return [dict(key=key, value=_encode_value(value)) for key, value in attributes.items()]
    else:
        return None


def _encode_events(
    events: Sequence[Event],
) -> list[dict[str, Any]] | None:
    if not events:
        return None

    encoded_events: list[dict[str, Any]] = []
    for event in events:
        encoded_event = _dict_not_none(
            name=event.name,
            time_unix_nano=event.timestamp,
            attributes=_encode_attributes(event.attributes),
            dropped_attributes_count=getattr(event.attributes, 'dropped', None),
        )
        encoded_events.append(encoded_event)
    return encoded_events


def _encode_links(links: Sequence[Link]) -> list[dict[str, Any]] | None:
    if not links:
        return None

    encoded_links: list[dict[str, Any]] = []
    for link in links:
        encoded_link = _dict_not_none(
            trace_id=_encode_trace_id(link.context.trace_id),
            span_id=_encode_span_id(link.context.span_id),
            attributes=_encode_attributes(link.attributes),
            dropped_attributes_count=getattr(link.attributes, 'dropped', None),
        )
        encoded_links.append(encoded_link)
    return encoded_links


def _encode_status(status: Status | None) -> dict[str, Any] | None:
    if status is None:
        return None

    return _dict_not_none(code=status.status_code.value, message=status.description)


def _encode_value(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {'stringValue': value}
    elif isinstance(value, bool):
        return {'boolValue': value}
    elif isinstance(value, int):
        return {'intValue': value}
    elif isinstance(value, float):
        return {'doubleValue': value}
    elif isinstance(value, bytes):
        return {'bytesValue': value}
    elif isinstance(value, Sequence):
        return {'arrayValue': [_encode_value(v) for v in value]}
    elif isinstance(value, Mapping):
        return {'kvlistValue': [{'key': str(key), 'value': _encode_value(value)} for key, value in value.items()]}
    else:
        raise ValueError(f'Invalid type {type(value)} of value {value}')


def _dict_not_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}
