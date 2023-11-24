from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import IO, Iterator, Literal, Sequence

from google.protobuf.json_format import MessageToJson
from opentelemetry.exporter.otlp.proto.common.trace_encoder import (
    encode_spans,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from typing_extensions import assert_never

from .._constants import DEFAULT_FALLBACK_FILE_NAME

HEADER = b'LOGFIRE BACKUP FILE\n'
VERSION = b'VERSION 1\n'


class FileSpanExporter(SpanExporter):
    def __init__(
        self,
        file_path: str | Path | IO[bytes],
    ) -> None:
        self.file_path = Path(file_path) if isinstance(file_path, str) else file_path
        self._lock = threading.Lock()
        self._file: IO[bytes] | None = None
        self._wrote_header = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            if not self._file:
                if isinstance(self.file_path, Path):
                    self._file = self.file_path.open('ab')
                else:
                    self._file = self.file_path
                self._file.seek(0, os.SEEK_END)
                if self._file.tell() == 0:
                    self._file.write(HEADER)
                    self._file.write(VERSION)
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
                self._file.flush()
                if self._file is not self.file_path:
                    # don't close the file if it was passed in
                    self._file.close()


class FileParser:
    MISSING_HEADER = 1
    MISSING_VERSION = 2
    MISSING_BEG = 3
    IN_MESSAGE = 4

    def __init__(self) -> None:
        self.state: Literal[1, 2, 3, 4] = self.MISSING_HEADER
        self.buffer = bytearray()
        self.message_size = 0

    def get_suggested_read_size(self) -> int:
        if self.state == self.MISSING_HEADER:
            return len(HEADER) - len(self.buffer)
        elif self.state == self.MISSING_VERSION:
            return len(VERSION) - len(self.buffer)
        elif self.state == self.MISSING_BEG:
            return 4 - len(self.buffer)
        elif self.state == self.IN_MESSAGE:
            return self.message_size - len(self.buffer)
        assert_never(self.state)

    def finish(self) -> None:
        if not self.buffer or self.state == self.MISSING_BEG:
            # either nothing was read or we completed a message
            return
        if self.state == self.MISSING_HEADER:
            raise InvalidFile(f"Invalid backup file (expected '{HEADER.strip()}' header)")
        elif self.state == self.MISSING_VERSION:
            raise InvalidFile(f"Invalid backup file (expected '{VERSION.strip()}' header)")
        elif self.state == self.IN_MESSAGE:
            raise InvalidFile('Invalid backup file (expected message end)')
        assert_never(self.state)

    def push(self, data: bytes) -> ExportTraceServiceRequest | None:
        self.buffer += data
        if self.state == self.MISSING_HEADER:
            if len(self.buffer) >= len(HEADER):
                if bytes(self.buffer[: len(HEADER)]) != HEADER:
                    raise InvalidFile(f"Invalid backup file (expected '{HEADER.strip()}' header)")
                self.buffer = self.buffer[len(HEADER) :]
                self.state = self.MISSING_VERSION
            return None
        elif self.state == self.MISSING_VERSION:
            if len(self.buffer) >= len(VERSION):
                if bytes(self.buffer[: len(VERSION)]) != VERSION:
                    raise InvalidFile(f"Invalid backup file (expected '{VERSION.strip()}' header)")
                self.buffer = self.buffer[len(VERSION) :]
                self.state = self.MISSING_BEG
            return None
        elif self.state == self.MISSING_BEG:
            if len(self.buffer) >= 4:
                self.message_size = int.from_bytes(self.buffer[:4], 'big')
                self.buffer = self.buffer[4:]
                self.state = self.IN_MESSAGE
        elif self.state == self.IN_MESSAGE:
            if len(self.buffer) >= self.message_size:
                data = bytes(self.buffer[: self.message_size])
                self.buffer = self.buffer[self.message_size :]
                self.state = self.MISSING_BEG
                return ExportTraceServiceRequest.FromString(data)
        return None


class InvalidFile(ValueError):
    """Raised when a dump file is invalid."""


def load_file(file_path: str | Path | IO[bytes] | None) -> Iterator[ExportTraceServiceRequest]:
    """Load a backup file.

    Args:
        file_path: The path to the backup file.

    Raises:
        ValueError: If the file is not a valid backup file.

    Returns: An iterator over each ExportTraceServiceRequest message in the backup file.
    """
    if file_path is None:
        file_path = Path(DEFAULT_FALLBACK_FILE_NAME)
    elif isinstance(file_path, str):
        file_path = Path(file_path)
    with file_path.open('rb') if isinstance(file_path, Path) else file_path as f:
        parser = FileParser()
        while True:
            data = f.read(parser.get_suggested_read_size())
            if not data:
                parser.finish()
                return
            message = parser.push(data)
            if message is not None:
                yield message


def to_json_lines(file_path: str | Path | IO[bytes] | None) -> Iterator[str]:
    """Convert a backup file to JSON lines.

    Args:
        file_path: The path to the backup file.

    Raises:
        ValueError: If the file is not a valid backup file.

    Returns: An iterator over each JSON line in the backup file.
    """
    for message in load_file(file_path):
        yield MessageToJson(message)
