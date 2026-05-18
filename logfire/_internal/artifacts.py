"""The `Artifact` type — binary blobs attached to spans out of band.

An `Artifact` wraps a binary blob (image, audio, PDF, large JSON, ...). When it is logged
as a span attribute, Logfire stores the blob in object storage and embeds only a small
reference object in the span, so the blob never travels through the telemetry pipeline
and is not subject to attribute size limits.

Artifacts are content-addressed: the SDK computes the blob's sha256 and that is its
identity. The same blob logged repeatedly is uploaded and stored once.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from abc import ABC, abstractmethod
from typing import IO, Any, Literal

__all__ = 'Artifact', 'UploadMode'

UploadMode = Literal['sync', 'background']
"""When an artifact's blob bytes are uploaded, relative to the logging call.

- `sync`: upload inline — the logging call returns only once the blob is stored, so the
  source bytes/file/handle may be freed, closed, or deleted immediately afterwards.
- `background`: hand the upload to a background thread — the logging call never blocks.
  Near-free for file-path sources (re-read from disk at upload time); holds the bytes in
  memory for in-memory `bytes` sources until the upload drains. If uploads cannot keep
  up, queued artifacts are dropped with a warning rather than stalling the program — use
  `sync` when delivery must be guaranteed.
"""

# The discriminator stamped on the reference object embedded in span attributes; the
# backend and frontend key off this to recognise an artifact reference.
ARTIFACT_REFERENCE_TYPE = 'logfire.artifact'

_HASH_CHUNK_SIZE = 1024 * 1024


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

    def __init__(self, data: bytes) -> None:
        self._data = bytes(data)

    def digest(self) -> tuple[str, int]:
        return hashlib.sha256(self._data).hexdigest(), len(self._data)

    def read(self) -> bytes:
        return self._data


class _PathSource(ArtifactSource):
    """A file on disk.

    Hashed and uploaded by reading the path, so a `background` upload of a file path
    holds no bytes in memory.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = os.fspath(path)

    def digest(self) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        with open(self._path, 'rb') as file:
            while chunk := file.read(_HASH_CHUNK_SIZE):
                hasher.update(chunk)
                size += len(chunk)
        return hasher.hexdigest(), size

    def read(self) -> bytes:
        with open(self._path, 'rb') as file:
            return file.read()


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

    def __init__(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload: UploadMode = 'background',
    ) -> None:
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
        self._configure(
            _BytesSource(data), filename=filename, content_type=content_type, upload=upload, guess_from=filename
        )

    @classmethod
    def from_file(
        cls,
        path: str | os.PathLike[str],
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload: UploadMode = 'background',
    ) -> Artifact:
        """Create an artifact from a file path.

        The file is read once to hash it and again to upload it, so a `background`
        upload of a file path holds no bytes in memory.

        Args:
            path: Path to the file.
            filename: Original filename to record. Defaults to the basename of `path`.
            content_type: MIME type. Guessed from the path/filename when omitted.
            upload: When to upload the blob — see [`UploadMode`][logfire.UploadMode].
        """
        artifact = cls.__new__(cls)
        artifact._configure(
            _PathSource(path),
            filename=filename or os.path.basename(os.fspath(path)),
            content_type=content_type,
            upload=upload,
            guess_from=filename or os.fspath(path),
        )
        return artifact

    @classmethod
    def from_file_handle(
        cls,
        handle: IO[bytes],
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload: UploadMode = 'background',
    ) -> Artifact:
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
        artifact = cls.__new__(cls)
        handle_name = getattr(handle, 'name', None)
        resolved_name = filename or (os.path.basename(handle_name) if isinstance(handle_name, str) else None)
        artifact._configure(
            _BytesSource(handle.read()),
            filename=resolved_name,
            content_type=content_type,
            upload=upload,
            guess_from=resolved_name or handle_name,
        )
        return artifact

    def _configure(
        self,
        source: ArtifactSource,
        *,
        filename: str | None,
        content_type: str | None,
        upload: UploadMode,
        guess_from: Any,
    ) -> None:
        self._source = source
        self.filename = filename
        self.upload: UploadMode = upload
        self.content_type = content_type or _guess_content_type(guess_from)
        self._digest: tuple[str, int] | None = None

    @property
    def sha256(self) -> str:
        """The hex sha256 of the blob — its content-addressed identity."""
        return self._compute()[0]

    @property
    def size_bytes(self) -> int:
        """The size of the blob in bytes."""
        return self._compute()[1]

    def _compute(self) -> tuple[str, int]:
        if self._digest is None:
            self._digest = self._source.digest()
        return self._digest

    def read(self) -> bytes:
        """Read the full blob into memory (used by the uploader)."""
        return self._source.read()

    def reference(self) -> dict[str, Any]:
        """The reference object embedded into the span attribute in place of the blob."""
        sha256, size_bytes = self._compute()
        reference: dict[str, Any] = {
            'type': ARTIFACT_REFERENCE_TYPE,
            'sha256': sha256,
            'content_type': self.content_type,
            'size_bytes': size_bytes,
        }
        if self.filename is not None:
            reference['filename'] = self.filename
        return reference


def _guess_content_type(name: Any) -> str:
    """Guess a MIME type from a filename/path, defaulting to `application/octet-stream`."""
    if isinstance(name, str):
        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
    return 'application/octet-stream'
