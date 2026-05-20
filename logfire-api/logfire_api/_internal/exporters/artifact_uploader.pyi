from _typeshed import Incomplete

from ..artifacts import Artifact as Artifact
from ..utils import log_internal_error as log_internal_error

DEFAULT_MAX_QUEUE_BYTES: Incomplete

class ArtifactUploader:
    """Uploads artifact blobs to the Logfire backend.

    Owns a daemon worker thread for `background` artifacts; `sync` artifacts are uploaded
    on the calling thread.
    """
    def __init__(self, *, base_url: str, token: str, max_queue_bytes: int = ...) -> None: ...
    def submit(self, artifact: Artifact) -> None:
        """Upload an artifact's blob — inline for `sync`, queued for `background`.

        A `background` submit **never blocks the caller**: if the queue is already over
        its byte budget, the artifact is dropped with a warning rather than applying
        backpressure. A `sync` submit uploads inline (and so blocks) by the caller's
        explicit choice. Never raises — upload failures are handled internally.
        """
    def flush(self, timeout: float | None = None) -> bool:
        """Block until queued background uploads have drained. Returns whether they did."""
    def shutdown(self, timeout: float = 5.0) -> None:
        """Drain in-flight uploads and stop the worker thread."""
