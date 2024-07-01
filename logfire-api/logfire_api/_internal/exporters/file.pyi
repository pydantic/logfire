from ..constants import DEFAULT_FALLBACK_FILE_NAME as DEFAULT_FALLBACK_FILE_NAME
from ..utils import ensure_data_dir_exists as ensure_data_dir_exists
from _typeshed import Incomplete
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan as ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter
from pathlib import Path
from typing import Generator, IO, Iterable, Iterator, Sequence

HEADER: bytes
VERSION: bytes

class Writer:
    def write_header(self) -> bytes: ...
    def write(self, spans: ExportTraceServiceRequest) -> Iterable[bytes]: ...

class WritingFallbackWarning(Warning): ...

class FileSpanExporter(SpanExporter):
    file_path: Incomplete
    def __init__(self, file_path: str | Path | IO[bytes], *, warn: bool = False) -> None: ...
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...
    def force_flush(self, timeout_millis: int = 30000) -> bool: ...
    def shutdown(self) -> None: ...

class FileParser:
    MISSING_HEADER: int
    MISSING_VERSION: int
    MISSING_BEG: int
    IN_MESSAGE: int
    state: Incomplete
    buffer: Incomplete
    message_size: int
    def __init__(self) -> None: ...
    def get_suggested_read_size(self) -> int: ...
    def finish(self) -> None: ...
    def push(self, data: bytes) -> Generator[ExportTraceServiceRequest, None, None]: ...

class InvalidFile(ValueError):
    """Raised when a dump file is invalid."""

def load_file(file_path: str | Path | IO[bytes] | None) -> Iterator[ExportTraceServiceRequest]:
    """Load a backup file.

    Args:
        file_path: The path to the backup file.

    Raises:
        ValueError: If the file is not a valid backup file.

    Returns:
        An iterator over each `ExportTraceServiceRequest` message in the backup file.
    """
def to_json_lines(file_path: str | Path | IO[bytes] | None) -> Iterator[str]:
    """Convert a backup file to JSON lines.

    Args:
        file_path: The path to the backup file.

    Raises:
        ValueError: If the file is not a valid backup file.

    Returns: An iterator over each JSON line in the backup file.
    """
