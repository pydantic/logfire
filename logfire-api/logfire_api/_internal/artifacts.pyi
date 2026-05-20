import os
from abc import ABC, abstractmethod
from typing import IO, Any

from _typeshed import Incomplete

__all__ = ['Artifact', 'UploadMode']

UploadMode: Incomplete

class ArtifactSource(ABC):
    """A source of artifact bytes — normalises bytes, files, and handles to one surface.

    Deliberately small so that streaming sources can be added later as a new subclass
    without touching `Artifact`, the upload handshake, or the backend.
    """
    @abstractmethod
    def digest(self) -> tuple[str, int]:
        """Return `(sha256_hex, size_bytes)` for the content."""
    @abstractmethod
    def read(self) -> bytes:
        """Return the full content as bytes, for upload."""

class _BytesSource(ArtifactSource):
    """An in-memory blob."""
    def __init__(self, data: bytes) -> None: ...
    def digest(self) -> tuple[str, int]: ...
    def read(self) -> bytes: ...

class _PathSource(ArtifactSource):
    """A file on disk.

    Hashed and uploaded by reading the path, so a `background` upload of a file path
    holds no bytes in memory.
    """
    def __init__(self, path: str | os.PathLike[str]) -> None: ...
    def digest(self) -> tuple[str, int]: ...
    def read(self) -> bytes: ...

class Artifact:
    """A binary blob to attach to a span — an image, audio clip, PDF, large JSON, etc.

    Pass an `Artifact` as a span or log attribute value. Logfire uploads the blob to
    object storage out of band and embeds a small reference in the span.

    Examples:
        ```python
        import logfire

        logfire.configure()

        # From a file path.
        logfire.info('chart generated', chart=logfire.Artifact.from_file('chart.png'))

        # From in-memory bytes.
        logfire.info('thumbnail', image=logfire.Artifact(png_bytes, content_type='image/png'))

        # From an open binary handle (including temporary / spooled files).
        with open('report.pdf', 'rb') as handle:
            logfire.info('report', report=logfire.Artifact.from_file_handle(handle))
        ```
    """
    def __init__(self, data: bytes, *, filename: str | None = None, content_type: str | None = None, upload: UploadMode = 'background') -> None:
        """Create an artifact from in-memory bytes.

        Args:
            data: The blob bytes.
            filename: Optional original filename, shown in the UI and used to guess the
                content type.
            content_type: MIME type of the blob. Guessed from `filename` when omitted,
                falling back to `application/octet-stream`.
            upload: When to upload the blob — see [`UploadMode`][logfire.UploadMode].
                Defaults to `background`.
        """
    @classmethod
    def from_file(cls, path: str | os.PathLike[str], *, filename: str | None = None, content_type: str | None = None, upload: UploadMode = 'background') -> Artifact:
        """Create an artifact from a file path.

        The file is read once to hash it and again to upload it, so a `background`
        upload of a file path holds no bytes in memory.

        Args:
            path: Path to the file.
            filename: Original filename to record. Defaults to the basename of `path`.
            content_type: MIME type. Guessed from the path/filename when omitted.
            upload: When to upload the blob — see [`UploadMode`][logfire.UploadMode].
        """
    @classmethod
    def from_file_handle(cls, handle: IO[bytes], *, filename: str | None = None, content_type: str | None = None, upload: UploadMode = 'background') -> Artifact:
        """Create an artifact from an open binary file handle.

        Works with any binary handle, including `tempfile.SpooledTemporaryFile` and
        `tempfile.NamedTemporaryFile`. The handle is read in full immediately, so the
        caller may close it as soon as this returns.

        Args:
            handle: An open binary (`'rb'`) file-like object.
            filename: Original filename to record. Defaults to the handle's `name`.
            content_type: MIME type. Guessed from the filename when omitted.
            upload: When to upload the blob — see [`UploadMode`][logfire.UploadMode].
        """
    @property
    def sha256(self) -> str:
        """The hex sha256 of the blob — its content-addressed identity."""
    @property
    def size_bytes(self) -> int:
        """The size of the blob in bytes."""
    def read(self) -> bytes:
        """Read the full blob into memory (used by the uploader)."""
    def reference(self) -> dict[str, Any]:
        """The reference object embedded into the span attribute in place of the blob."""
