from __future__ import annotations

import threading
from pathlib import Path
from typing import IO, Iterator, Sequence

from opentelemetry.exporter.otlp.proto.common.trace_encoder import (
    encode_spans,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .._constants import DEFAULT_FALLBACK_FILE_NAME


class FileSpanExporter(SpanExporter):
    def __init__(
        self,
        file_path: str | Path,
    ) -> None:
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
        self._file: IO[bytes] | None = None

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            if not self._file:
                self._file = self.file_path.open('ab')
                self._file.write(b'LOGFIRE BACKUP FILE\n')
                self._file.write(b'VERSION 1\n')
            encoded_spans = encode_spans(spans)
            size = encoded_spans.ByteSize()
            # we can represent up to a 4GB message
            self._file.write(size.to_bytes(4, 'big'))
            self._file.write(encoded_spans.SerializeToString())
            self._file.flush()
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def shutdown(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()


def load_file(file_path: str | Path | None) -> Iterator[ExportTraceServiceRequest]:
    """Load a backup file.

    Args:
        file_path: The path to the backup file.

    Raises:
        ValueError: If the file is not a valid backup file.

    Returns: An iterator over each ExportTraceServiceRequest message in the backup file.
    """
    file_path = Path(file_path) if file_path else Path(DEFAULT_FALLBACK_FILE_NAME)
    with file_path.open('rb') as f:
        if f.readline() != b'LOGFIRE BACKUP FILE\n':
            raise ValueError("Invalid backup file (expected 'LOGFIRE BACKUP FILE' header)")
        if f.readline() != b'VERSION 1\n':
            version = f.readline().decode('utf-8').strip()
            raise ValueError(f"Invalid backup file version '{version}' (expected 1)")
        while True:
            size = int.from_bytes(f.read(4), 'big')
            if not size:
                break
            yield ExportTraceServiceRequest.FromString(f.read(size))
