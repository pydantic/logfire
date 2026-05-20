"""Background uploader for artifact blobs.

Artifact blobs are uploaded out of band from telemetry: the upload (a register / PUT /
finalize handshake against the Logfire backend) never blocks span export. A `sync`
artifact is uploaded inline on the logging thread (the caller's explicit choice); a
`background` artifact is handed to a worker thread and **never blocks the caller** —
if the worker's queue is over its byte budget the artifact is dropped with a warning
rather than applying backpressure.
"""

from __future__ import annotations

import queue
import threading
import time
import warnings
from urllib.parse import urljoin

import requests

from ..artifacts import Artifact
from ..utils import log_internal_error

# Default ceiling on bytes queued for background upload. When exceeded, `submit` blocks.
DEFAULT_MAX_QUEUE_BYTES = 64 * 1024 * 1024

# Per-HTTP-request timeout for the upload handshake.
_REQUEST_TIMEOUT = 30


class ArtifactUploader:
    """Uploads artifact blobs to the Logfire backend.

    Owns a daemon worker thread for `background` artifacts; `sync` artifacts are uploaded
    on the calling thread.
    """

    def __init__(self, *, base_url: str, token: str, max_queue_bytes: int = DEFAULT_MAX_QUEUE_BYTES) -> None:
        self._base_url = base_url
        self._auth = {'Authorization': f'Bearer {token}'}
        self._max_queue_bytes = max_queue_bytes
        self._queue: queue.Queue[Artifact | None] = queue.Queue()
        # Guards `_queued_bytes`; notified whenever an upload finishes or is dequeued.
        self._capacity = threading.Condition()
        self._queued_bytes = 0
        self._thread = threading.Thread(target=self._run, name='logfire-artifact-uploader', daemon=True)
        self._thread.start()

    def submit(self, artifact: Artifact) -> None:
        """Upload an artifact's blob — inline for `sync`, queued for `background`.

        A `background` submit **never blocks the caller**: if the queue is already over
        its byte budget, the artifact is dropped with a warning rather than applying
        backpressure. A `sync` submit uploads inline (and so blocks) by the caller's
        explicit choice. Never raises — upload failures are handled internally.
        """
        if artifact.upload == 'sync':
            self._run_upload(artifact)
            return

        size = artifact.size_bytes
        with self._capacity:
            # Drop rather than block: artifact uploads must never stall the program.
            # An empty queue always admits one artifact, so a lone large blob still
            # uploads even if it alone exceeds the budget.
            if self._queued_bytes and self._queued_bytes + size > self._max_queue_bytes:
                warnings.warn(
                    f'Artifact upload queue is full ({self._queued_bytes} bytes queued); '
                    f'dropping background artifact ({size} bytes). '
                    'Pass upload="sync" to guarantee delivery.',
                )
                return
            self._queued_bytes += size
        self._queue.put(artifact)

    def flush(self, timeout: float | None = None) -> bool:
        """Block until queued background uploads have drained. Returns whether they did."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._capacity:
            while self._queued_bytes:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._capacity.wait(remaining)
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Drain in-flight uploads and stop the worker thread."""
        self.flush(timeout)
        self._queue.put(None)
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            artifact = self._queue.get()
            if artifact is None:
                return
            try:
                self._run_upload(artifact)
            finally:
                with self._capacity:
                    self._queued_bytes -= artifact.size_bytes
                    self._capacity.notify_all()

    def _run_upload(self, artifact: Artifact) -> None:
        try:
            self._upload(artifact)
        except requests.RequestException:
            # Network/HTTP failures are operational, not bugs: the artifact reference is
            # still recorded on the span, the blob just isn't stored. Best-effort upload —
            # never crash the caller's logging call over it.
            pass
        except Exception:
            log_internal_error()

    def _upload(self, artifact: Artifact) -> None:
        """Run the register / PUT / finalize handshake for one artifact."""
        reference = artifact.reference()
        sha256 = reference['sha256']

        registered = requests.post(
            urljoin(self._base_url, '/v1/artifacts'),
            json={
                'sha256': sha256,
                'size_bytes': reference['size_bytes'],
                'content_type': reference['content_type'],
                'filename': reference.get('filename'),
            },
            headers=self._auth,
            timeout=_REQUEST_TIMEOUT,
        )
        registered.raise_for_status()
        body = registered.json()
        if body['status'] == 'exists':
            # The blob is already stored (content-addressed dedup) — nothing to upload.
            return

        target = body['upload']
        # Signed object-store URLs are self-authenticating; sending the bearer token
        # there can break the signature, so only the backend `/blob` endpoint gets auth.
        put_headers = self._auth if target['requires_auth'] else {}
        put = requests.request(
            target['method'], target['url'], data=artifact.read(), headers=put_headers, timeout=_REQUEST_TIMEOUT
        )
        put.raise_for_status()

        finalized = requests.post(
            urljoin(self._base_url, f'/v1/artifacts/{sha256}/finalize'),
            headers=self._auth,
            timeout=_REQUEST_TIMEOUT,
        )
        finalized.raise_for_status()
