import gzip
import zlib
from io import BytesIO
from time import sleep

from google.protobuf.json_format import MessageToJson
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter, _expo, _logger
from opentelemetry.sdk.trace.export import SpanExportResult


class HttpJsonSpanExporter(OTLPSpanExporter):
    def export(self, spans) -> SpanExportResult:
        # After the call to Shutdown subsequent calls to Export are
        # not allowed and should return a Failure result.
        if self._shutdown:
            _logger.warning('Exporter already shutdown, ignoring batch')
            return SpanExportResult.FAILURE

        # FIXME: This encodes bytes fields (spanid and traceid) as base64 strings
        # but the OTEL spec requires them to be hex strings
        # (see https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding)
        # We're handling this server-side for now but it means our data is not OTEL compliant
        serialized_data = MessageToJson(encode_spans(spans), use_integers_for_enums=True)

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
