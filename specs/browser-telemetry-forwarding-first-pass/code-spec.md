# OTLP Telemetry Forwarding First Pass Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

**Architecture diagrams are in [diagrams](diagrams.md).**

This code spec only covers behavior that changes in the first pass. Preserved helper behavior and explicit scope exclusions stay in the prose spec.

**Part 1: Changed Files**

**`logfire/experimental/forwarding.py` remains the public experimental entry point.** *(implements "This first pass keeps the existing helper API and changes the implementation behind it", "Accepted OTLP payloads are queued locally before any Logfire network I/O")*
The module keeps exporting `ForwardExportRequestResponse`, `forward_export_request`, and `logfire_proxy` with their existing public call styles. The changed code is behind those shapes: the helpers become request-admission adapters that validate request-level inputs, resolve the relevant `LogfireConfig`, and submit opaque payload bytes to the config-owned forwarding manager. `forward_export_request()` enforces the shared 50 MiB default request body limit for direct calls, while `logfire_proxy()` continues to expose its existing `max_body_size` option and delegates using that configured limit. Their docstrings should describe local forwarding admission rather than synchronous proxying to Logfire.

**`logfire/_internal/forwarding.py` is a new internal forwarding lifecycle module.** *(implements "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call", "Destination pipelines are separated by resolved backend URL")*
The module owns all queue, worker, response-encoding, and forwarding destination structures. It is internal to Logfire configuration and is not exported from `logfire.experimental`.

**`logfire/_internal/config.py` owns the forwarding manager.** *(implements "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call", "Forwarding participates in Logfire flush and shutdown")*
`LogfireConfig` gains a private forwarding manager that follows the existing Logfire export lifecycle. Configuration collects forwarding destinations only inside the existing `if self.send_to_logfire:` token/exporter construction path, then builds the new forwarding manager from that destination list. If `send_to_logfire=False`, no forwarding pipelines are created, even when `config.token` is set. The manager is reset only as part of configuration lifecycle changes. `LogfireConfig.force_flush()` includes forwarding manager flushing of memory queues and active immediate sends while preserving the existing full-timeout-per-component flush pattern.

```python
class LogfireConfig(_LogfireConfigData):
    _otlp_forwarding: OTLPForwardingManager
```

`_otlp_forwarding` is the private owner for forwarding queues and transport resources associated with this config. Public forwarding helpers reach it through the selected `Logfire` instance's config; normal instrumentation exporters do not call it.

**`logfire/_internal/main.py` shuts down forwarding with the Logfire instance.** *(implements "Forwarding participates in Logfire flush and shutdown", "Post-shutdown forwarding calls are locally dropped")*
`Logfire.shutdown()` includes forwarding manager shutdown in the same overall deadline accounting used for variables, traces, and metrics for queued memory drain. With `flush=True`, shutdown closes forwarding admission before draining memory work, then waits for any active immediate forwarding send to finish before closing forwarding sessions and returning. With `flush=False`, shutdown still closes forwarding admission and sessions, but it passes `drain_queued=False` so queued forwarding work is dropped rather than flushed.

**Markdown docs changes are deferred to the docs source repo.** *(implements "Documentation of externally driven ingress is deferred to the docs source repo", "CORS documentation is deferred with the ingress documentation")*
The browser integration markdown page that previously lived at `docs/integrations/javascript/browser.md` has moved out of this repository, so this PR does not change that file. The deferred docs work should port the intent captured in `ignoreme/workflow/patches/pr-1940-browser.patch`: explain that the Python endpoint is externally driven telemetry ingress, that accepted responses mean local admission rather than remote delivery, that Python-side scrubbing does not apply to opaque inbound payloads, and that users should protect the route with their normal app controls.

**Part 2: Internal Data Shapes**

**Forwarding requests are opaque destination-independent payload records.** *(implements "The forwarding endpoint is an ingress adapter, not a transparent HTTP proxy", "The first pass supports protobuf and JSON OTLP payload representations")*
The admission path creates one `ForwardingRequest` after route, content type, and request body-size checks pass, before active forwarding destination checks and backend-url fanout. The same request object can be enqueued into multiple backend-url pipelines.

```python
ForwardingPath = Literal['/v1/traces', '/v1/logs', '/v1/metrics']


@dataclass(frozen=True)
class ForwardingRequest:
    """Opaque inbound OTLP payload admitted for asynchronous forwarding."""

    path: ForwardingPath
    body: bytes
    content_type: ForwardingContentType
    headers: Mapping[str, str]

    @property
    def path_config(self) -> ForwardingPathConfig:
        """Return the forwarding metadata for this request path."""


class ForwardingContentType(Enum):
    PROTOBUF = 'application/x-protobuf'
    JSON = 'application/json'
```

`ForwardingRequest` is created once for a valid inbound request and is shared by reference across backend-url queues.

`path` selects the Logfire OTLP endpoint and the matching OTLP export response message. `path_config` returns the centralized forwarding metadata for that path. `body` is the opaque payload forwarded to Logfire and the byte value counted against each backend-url memory queue. `content_type` records the inferred OTLP representation and drives the local response representation. `headers` stores a copied read-only canonical snapshot of only the whitelisted inbound headers needed to build the Logfire-bound request: original `Content-Type`, optional `Content-Encoding`, and the composed Logfire proxy `User-Agent`. Client `Authorization`, cookies, host headers, and other inbound headers are not retained on the queued request.

`ForwardingContentType.PROTOBUF` represents `application/x-protobuf` requests and responses. `ForwardingContentType.JSON` represents `application/json` requests and responses.

**Path-specific forwarding metadata is centralized.** *(implements "Forwarding send timeout follows OTLP HTTP exporter timeout configuration", "Response encoding matches the inferred request representation", "Partial success has zero rejected records and an explanatory message")*
The internal module keeps path-specific timeout and response metadata in one table keyed by forwarding path.

```python
@dataclass(frozen=True)
class ForwardingPathConfig:
    timeout_env: str
    default_timeout: float
    partial_success_rejected_attribute: str
    response_message_type: type[Any]

    def timeout(self) -> float:
        """Return the OTLP HTTP exporter timeout, in seconds, for this signal path."""


FORWARDING_CONFIGS: dict[ForwardingPath, ForwardingPathConfig]
```

`timeout_env` stores the signal-specific OpenTelemetry timeout environment variable for the path. `default_timeout` stores the matching OTLP HTTP exporter default timeout. `partial_success_rejected_attribute` identifies the OTLP response field that must be set to `0` for local partial-success responses. `response_message_type` stores the generated OTLP export response message class for the path. This avoids parallel path maps for timeout resolution, path validation, response message selection, and partial-success field selection.

**Destination resolution follows the normal Logfire exporter token loop.** *(implements "Destination pipelines are separated by resolved backend URL", "Forwarding uses every active Logfire export write token grouped by backend URL")*
Inside the same `for token in token_list:` loop that constructs normal Logfire OTLP exporters, after the code resolves `base_url = self.advanced.generate_base_url(token)`, the configuration records that `(base_url, token)` pair for the forwarding manager. The new manager is constructed from the complete destination list after exporter construction. If a pipeline for the resolved backend URL does not already exist, manager construction creates it immediately. It then appends each token to that pipeline's token list. This means forwarding uses exactly the write tokens and backend URLs used by normal Logfire export.

When `send_to_logfire=False`, the exporter-construction loop does not run and the manager remains empty. Forwarding requests against an empty manager return the local forbidden response before queue admission.

The backend URL to pipeline mapping and each pipeline's token list are constant after configuration initialization completes. Reconfiguration shuts down the old manager and creates a new empty manager that is populated by the new configuration's exporter-construction loop.

**Admission result records only the response class.** *(implements "A full backend-URL queue does not block other backend URLs", "Locally dropped valid payloads return OTLP partial success")*
The forwarding manager returns the local response class needed by the public adapter. The manager may use per-backend URL outcomes when constructing the message, but does not expose those intermediate outcomes as returned structure.

```python
@dataclass(frozen=True)
class ForwardingAdmissionResult:
    """Local admission response choice after enqueue/drop decisions."""

    response: Literal['success', 'partial_success']
    message: str | None
```

`response` is consumed by `forward_export_request()` to choose either the empty OTLP success response or the OTLP partial-success response. `message` is used only for partial success; the manager may include local drop context such as queue-full or shutdown state.

**Each backend URL has one mutable memory pipeline state object.** *(implements "Destination pipelines are separated by resolved backend URL", "Local queueing uses memory first", "Each backend-URL memory queue has hardcoded byte and item limits", "The forwarding worker is non-daemon and lifecycle-managed")*
The pipeline owns memory queue bytes, worker state, and one long-lived `OTLPExporterHttpSession` for the backend URL.

```python
class OTLPForwardingPipeline:
    """Memory queue and sender lifecycle for one resolved Logfire backend URL."""

    base_url: str
    session: OTLPExporterHttpSession
    queue: deque[ForwardingRequest]
    max_queued_body_bytes: int
    max_queued_items: int
    worker: Thread | None
    closed: bool
    condition: Condition
    tokens: list[str]

    @property
    def queued_body_bytes(self) -> int:
        """Return the bytes currently held in the memory queue."""
```

`base_url` identifies the backend URL this pipeline owns and is used to construct trace, log, and metric export URLs. `session` is the long-lived `OTLPExporterHttpSession` shared by sends for all tokens targeting this backend URL, so retry ownership stays with the existing OTLP session and `DiskRetryer`. `tokens` is the active Logfire export write token list for the pipeline's backend URL; `_send()` iterates those tokens to fan out the same payload with per-token authorization.

`queue` holds memory-admitted `ForwardingRequest` objects until their immediate send attempt completes. The worker peeks at the first item, sends it once per token, and removes it in a `finally` block after any send outcome. `queued_body_bytes` is a computed property over `queue`, so one payload counts once for the backend URL regardless of how many tokens the pipeline fans out to during send. `max_queued_body_bytes` is the admission ceiling for `queued_body_bytes`, and `max_queued_items` is the admission ceiling for `len(queue)`.

`worker` is the non-daemon sender thread for this pipeline, or `None` while no worker is active. A worker exits after draining current memory work, and later accepted enqueue calls may create a new worker while the pipeline remains open. `enqueue()` owns this lazy worker creation inline after admitting work. `closed` blocks new enqueue attempts and marks the pipeline as shutting down; it is an admission flag, not a worker stop flag. When `drain_queued=True`, already-queued memory work may still drain after `closed` becomes true. When `drain_queued=False`, shutdown explicitly drops queued work before waiting for any currently live worker. `condition` protects `queue`, `worker`, and `closed`, and is the synchronization point used by enqueue, worker wakeups, flush waits, and shutdown waits.

**The hardcoded queue limits are named once in the internal module.** *(implements "Each backend-URL memory queue has hardcoded byte and item limits")*

```python
OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES = 64 * 1024 * 1024
OTLP_FORWARDING_MAX_QUEUED_ITEMS = 1000
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024
```

`OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES` is passed into each new `OTLPForwardingPipeline` as `max_queued_body_bytes`, and `OTLP_FORWARDING_MAX_QUEUED_ITEMS` is passed as `max_queued_items`. Neither queue limit is exposed as a public or per-request option.

`OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES` is the default direct-request admission limit and the default ASGI helper `max_body_size`. The ASGI helper can still receive an explicit `max_body_size`; that value is passed to request validation for the delegated request so the existing ASGI configurability remains honored.

**Part 3: Internal APIs**

**`OTLPForwardingManager` is the LogfireConfig-owned coordinator.** *(implements "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call", "Forwarding participates in Logfire flush and shutdown")*
The manager has no public experimental import path. It accepts destinations from the normal Logfire exporter construction path, owns backend-url pipelines, and coordinates flush/shutdown.

```python
class OTLPForwardingManager:
    """Configuration-owned OTLP forwarding lifecycle."""

    pipelines: dict[str, OTLPForwardingPipeline]
    closed: bool

    def __init__(
        self,
        destinations: Sequence[tuple[str, str]],
        *,
        server_response_hook: ServerResponseCallback | None = None,
    ) -> None:
        """Create backend pipelines for the resolved forwarding destinations."""

    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult:
        """Admit one validated OTLP request into destination pipelines."""

    def has_destinations(self) -> bool:
        """Return whether forwarding has any Logfire export destinations."""

    def force_flush(self, timeout_millis: int) -> bool:
        """Wait for forwarding queues to finish queued work and active sends."""

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        """Close admission, optionally drop memory work, wait workers, then close idle transport resources."""
```

`pipelines` maps resolved backend URL to the single pipeline that owns that backend's memory queue, token list, and session. `closed` marks manager-level shutdown and makes future submissions return partial success without creating pipelines. The manager does not need its own lock because destination pipelines are fixed during construction and each pipeline owns its queue, closed state, worker state, and session-close synchronization.

The constructor receives the destination pairs collected while configuring normal Logfire export, from the same token loop that creates trace, metric, and log exporters, plus the resolved advanced response hook for the configuration that owns the manager. It creates the backend-url pipeline immediately on the first token for that URL and records additional tokens for the same URL without creating another pipeline. New pipeline creation constructs a fresh `OTLPExporterHttpSession` and installs the resolved `server_response_hook` on it before the session is used for sends.

`has_destinations()` is called by `forward_export_request()` before queue admission to decide whether the selected configuration has any active forwarding destination.

`submit()` is called by `forward_export_request()` after request validation. It reads the existing pipelines and enqueues the same `ForwardingRequest` independently into each backend URL pipeline. If no destinations were registered, submit is not called; the adapter returns the local forbidden response. `force_flush()` waits for manager-owned forwarding queues within the flush timeout. `shutdown(drain_queued=True)` closes admission, waits for queues and workers within the caller timeout, and drops queued memory work if the deadline expires first. `shutdown(drain_queued=False)` is used by `Logfire.shutdown(flush=False)`; it closes admission, drops memory-queued work before waiting for workers, closes sessions when workers finish, and does not report incomplete merely because queued work was deliberately dropped.

The manager applies one remaining-time budget across all pipeline flush calls and forwarding shutdown. `force_flush()` returns `False` if the deadline is exhausted before the pipeline queue becomes empty. Since the worker keeps the current send at the front of the queue until the send attempt finishes, queue emptiness covers both queued memory work and active immediate sends. `shutdown(drain_queued=True)` returns `False` if the queue does not become empty or the worker does not exit before the deadline; in that case it drops queued memory work and leaves final session close to worker cleanup. `shutdown(drain_queued=False)` drops queued memory work before waiting for any live worker and does not return `False` merely because it deliberately dropped queued memory work.

**The manager exposes request validation helpers for the public adapter.** *(implements "`Content-Type` supports protobuf and JSON OTLP", "The helper forwards only whitelisted representation headers")*
These helpers live beside the manager so header and response representation decisions are shared by forwarding adapters without introducing public API.

```python
def parse_forwarding_content_type(content_type: str) -> ForwardingContentType | None:
    """Return the inferred OTLP response representation, or None for unsupported input."""


def build_forwarding_request(
    *,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    max_body_size: int = OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
) -> ForwardingRequest | ForwardingErrorResponse:
    """Build an opaque forwarding request or a local validation error response."""
```

`parse_forwarding_content_type()` is used during admission before constructing `ForwardingRequest`. It inspects an already-extracted `Content-Type` header value for the supported representation markers `application/x-protobuf` and `application/json` case-insensitively. It does not validate the header as a media type; backend validation owns actual header semantics for the forwarded request. Empty values or values without a supported representation marker map to `None`, and `None` maps to the local 415 response. Missing `Content-Type` is handled by `build_forwarding_request()` before calling this parser.

`build_forwarding_request()` is the shared request-level adapter for path, representation header, body size, and whitelisted header extraction. It rejects bodies larger than `max_body_size` with the local 413 response and otherwise keeps the payload opaque. Header extraction uses case-insensitive lookups for `Content-Type`, `Content-Encoding`, and `User-Agent`. A successful request stores both the inferred `ForwardingContentType` and a copied whitelisted header snapshot; successful output proceeds to manager submission. `ForwardingErrorResponse` remains an internal validation shape and must be adapted into `ForwardExportRequestResponse` at the public adapter boundary.

**Response builders encode local success and partial success.** *(implements "Response encoding matches the inferred request representation", "Accepted queued payloads return local OTLP success", "Locally dropped valid payloads return OTLP partial success")*
The response builder creates empty OTLP success for complete local acceptance and partial success with rejected count `0` plus an explanatory message for local queue drops.

```python
def build_success_response(request: ForwardingRequest) -> ForwardExportRequestResponse:
    """Return an HTTP 200 empty OTLP export response in the request representation."""


def build_partial_success_response(
    request: ForwardingRequest,
    *,
    message: str,
) -> ForwardExportRequestResponse:
    """Return an HTTP 200 OTLP partial-success response with rejected count 0."""
```

`build_success_response()` is used when `ForwardingAdmissionResult.response` is `success`. It uses `request.path` to select the signal-specific OTLP export response message and `request.content_type` to serialize the response representation. The returned `ForwardExportRequestResponse.headers` must include `Content-Type` set from `request.content_type.value`.

`build_partial_success_response()` is used when `ForwardingAdmissionResult.response` is `partial_success`. It uses the same path and content-type selection as success, and stores `message` as the OTLP partial-success explanatory text. The returned `ForwardExportRequestResponse.headers` must include `Content-Type` set from `request.content_type.value`.

The response `Content-Type` header uses `request.content_type.value`, so it is `application/x-protobuf` for `ForwardingContentType.PROTOBUF` and `application/json` for `ForwardingContentType.JSON`. Unlike the Logfire-bound request `Content-Type`, response `Content-Type` is the canonical inferred representation and does not preserve inbound request header parameters or other text.

**Validation errors remain response objects.** *(implements "The forwarding endpoint is an ingress adapter, not a transparent HTTP proxy")*
Internal validation failure shapes preserve the public response dataclass boundary instead of raising framework-specific exceptions.

```python
@dataclass(frozen=True)
class ForwardingErrorResponse:
    """Local validation failure response before queue admission."""

    status_code: int
    content: bytes
```

`status_code` is the local HTTP response code for validation failures such as missing token or unsupported content type. `content` is the local error body returned without touching the forwarding manager. Public adapters wrap these internal failures with their own response headers.

**No active forwarding destination maps to forbidden.** *(implements "Requests with no active forwarding destination are rejected with 403")*
The forwarding adapter returns a local `403` response when the resolved Logfire configuration has no registered forwarding destinations, including `send_to_logfire=False`, before touching queue state.

**Missing or unsupported representation maps to unsupported media type.** *(implements "`Content-Type` supports protobuf and JSON OTLP")*
The forwarding adapter returns a local `415` response when request headers omit `Content-Type` or the header value does not identify a supported OTLP protobuf or JSON representation marker.

**`OTLPForwardingPipeline` owns queue admission and sending.** *(implements "Accepted OTLP payloads are queued locally before any Logfire network I/O", "A full backend-URL queue does not block other backend URLs", "Forwarding sends use the existing OTLP session retry ownership")*
The pipeline accepts work if its memory byte and item budgets allow it, starts a non-daemon worker when needed, and sends queued payloads with its long-lived `OTLPExporterHttpSession`.

```python
class OTLPForwardingPipeline:
    def enqueue(self, request: ForwardingRequest) -> bool:
        """Try to enqueue one request for this backend URL."""

    def force_flush(self, timeout_millis: int) -> bool:
        """Wait until the memory queue is empty or the timeout expires."""

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        """Close admission, optionally drop memory work, wait worker, then close the idle session."""

    def _run(self) -> None:
        """Run the forwarding worker for this backend URL."""

    def _send(self, request: ForwardingRequest) -> None:
        """Send one queued payload once per token for this backend URL."""
```

`enqueue()` is called by the manager once per backend-url group and returns whether this pipeline accepted the item into memory. `force_flush()` is called by the manager to wait for queued memory work and active immediate sends for this one backend URL. `shutdown(drain_queued=True)` is called by the manager when the config or Logfire instance shuts down with flush enabled; it closes admission, waits for the queue to become empty and the worker to finish until the deadline expires, drops queued work if the deadline expires first, and closes the session only when the worker has finished. `shutdown(drain_queued=False)` closes admission, immediately drops queued memory work, then waits for any live worker before closing the session.

`enqueue()` starts a non-daemon worker while holding `condition` when queued work exists and no live worker is recorded, including after a previous worker drained the queue and exited. `_run()` is the worker target: it peeks at the first queued item, calls `_send()` inside a `try` block, removes that item from the queue in a `finally` block after the immediate send attempt completes if shutdown did not already drop it, and notifies flush/shutdown waiters when queued work changes. `_run()` exits when the memory queue is empty; it must not treat `closed=True` as a reason to abandon queued work when `drain_queued=True`. Before returning, `_run()` clears worker state while holding `condition` so future enqueue can create a new worker and shutdown can observe that no non-daemon worker remains alive. `_send()` performs the token fanout for one queued request and delegates each Logfire-bound request to `OTLPExporterHttpSession.post()`.

**Pipeline sends use per-token authorization with shared backend transport.** *(implements "Forwarding uses every active Logfire export write token grouped by backend URL", "Server authentication headers are injected, not forwarded from the client")*
Each queued payload is sent once per active Logfire export token in the backend-url group. `build_forwarding_request()` stores the whitelisted representation headers and composed Logfire proxy `User-Agent` once on the request. `_send()` copies that snapshot for each token and injects the active Logfire export write token as `Authorization`, so each token send receives a fresh header dictionary. The emitted `Content-Type` header preserves the original inbound field value.

**Worker send exceptions are contained at token and queued-item boundaries.** *(implements "Forwarding worker send failures are contained")*
`OTLPExporterHttpSession.post()` may raise after performing its immediate retry or after adding a failed request to `DiskRetryer`. `_send()` catches exceptions around each per-token `post()` call, logs or suppresses the exception locally, and continues with the remaining tokens in the pipeline token list. A failed token send must not skip later token sends for the same backend URL.

`_run()` also protects the queued-item boundary: if `_send()` raises unexpectedly despite per-token containment, `_run()` logs or suppresses that exception, still removes the item from the queue in `finally`, and then continues draining later queued items even if admission has been closed for shutdown. No send exception may terminate the worker while queued memory work remains or leave queue bytes stale.

**Forwarding timeout resolution mirrors OTLP HTTP exporters.** *(implements "Forwarding send timeout follows OTLP HTTP exporter timeout configuration")*
The worker resolves an explicit request timeout for each send from the queued request path by reading `request.path_config.timeout()`. `ForwardingPathConfig.timeout()` follows the same signal-specific environment variable precedence and default as the OpenTelemetry Python OTLP HTTP exporters.

For `/v1/traces`, the helper reads `OTEL_EXPORTER_OTLP_TRACES_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the trace OTLP HTTP exporter default timeout. For `/v1/logs`, it reads `OTEL_EXPORTER_OTLP_LOGS_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the logs OTLP HTTP exporter default timeout. For `/v1/metrics`, it reads `OTEL_EXPORTER_OTLP_METRICS_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the metrics OTLP HTTP exporter default timeout.

This timeout is passed as the `timeout` keyword argument to `OTLPExporterHttpSession.post()`. Flush and shutdown timeouts do not rewrite the per-send timeout. Flush timeout bounds how long the caller waits for forwarding queues to empty. Shutdown timeout bounds how long the caller waits for queued work and workers after admission is closed; with `drain_queued=False`, shutdown drops queued memory work before waiting for workers.

**Part 4: Call Relationships**

**`logfire_proxy()` continues to read and bound the body, then delegates admission.** *(implements "Accepted OTLP payloads are queued locally before any Logfire network I/O")*
The ASGI helper reads the request body under the configured request body limit, extracts the path parameter, and calls `forward_export_request()` through the existing threadpool boundary while passing along that same configured request body limit.

**`forward_export_request()` validates, submits, and locally responds.** *(implements "The forwarding endpoint is an ingress adapter, not a transparent HTTP proxy", "Accepted queued payloads return local OTLP success", "Locally dropped valid payloads return OTLP partial success")*
The low-level helper resolves the Logfire instance, builds a `ForwardingRequest` using the applicable request body limit, checks `logfire_instance.config._otlp_forwarding.has_destinations()`, returns local `403` if no destinations were registered, otherwise calls `logfire_instance.config._otlp_forwarding.submit()`, and maps the admission result to an OTLP success or partial-success response.

```python
def forward_export_request(
    *,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    logfire_instance: logfire.Logfire | None = None,
    max_body_size: int = OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
) -> ForwardExportRequestResponse:
    ...
```

Existing direct call sites remain valid because `max_body_size` is keyword-only and defaults to the preserved 50 MiB request limit. `logfire_proxy()` passes its existing configured `max_body_size` through to preserve ASGI helper configurability.

**`OTLPForwardingManager.submit()` uses manager-lifetime backend-url pipelines.** *(implements "Forwarding uses every active Logfire export write token grouped by backend URL", "Destination pipelines are separated by resolved backend URL")*
The manager reads the current pipeline values and enqueues into each backend pipeline independently. Submit does not create pipelines; pipelines are created only by manager construction from the normal Logfire exporter destination list, and each pipeline carries the token list for its backend URL.

**`OTLPForwardingPipeline._send()` delegates retry ownership to `OTLPExporterHttpSession.post()`.** *(implements "Forwarding sends use the existing OTLP session retry ownership")*
The worker performs one immediate send attempt per pipeline token through the pipeline session, passing `timeout=request.path_config.timeout()`. Retryable transport failures are handled by `OTLPExporterHttpSession` and its `DiskRetryer`, not by queue-level retry logic. Any exception re-raised by the session after that retry handling is contained by `_send()`/`_run()` so the forwarding worker continues draining.

**`LogfireConfig.force_flush()` calls the forwarding manager before returning.** *(implements "Forwarding participates in Logfire flush and shutdown")*
The config-level flush method preserves the existing `force_flush()` structure: meter, logger, forwarding, and tracer flush calls each receive the original `timeout_millis` value rather than sharing one aggregate deadline. The forwarding manager is called before the final tracer flush return, and its boolean result is not combined into the return value, matching the current behavior where meter and logger flush results do not change the returned tracer result.

TODO: Address the pre-existing `LogfireConfig.force_flush()` result aggregation bug in a follow-up rather than in this forwarding PR.

**`LogfireConfig.configure()` replaces forwarding lifecycle with configuration lifecycle.** *(implements "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call")*
Reconfiguration collects forwarding destinations while the existing `send_to_logfire` branch resolves tokens and backend URLs, including credentials-derived values, from the same loop that constructs normal exporters. After exporter construction succeeds, configuration installs a fresh manager built from that destination list and closes the previous config-owned forwarding manager.

**`Logfire.shutdown()` closes forwarding admission before provider shutdown completes.** *(implements "Forwarding participates in Logfire flush and shutdown", "Post-shutdown forwarding calls are locally dropped")*
Shutdown calls the config-owned manager with the remaining deadline. With `flush=True`, the manager waits for forwarding queues and workers within that deadline and drops queued memory work if the deadline expires. With `flush=False`, shutdown still calls the manager, but passes `drain_queued=False` so queued memory work is dropped before waiting for workers. After this point, otherwise valid forwarding calls map to partial success and do not recreate pipelines.

**Part 5: Response Representations**

**Protobuf responses use OTLP export response messages.** *(implements "Response encoding matches the inferred request representation", "Accepted queued payloads return local OTLP success", "Locally dropped valid payloads return OTLP partial success")*
The implementation uses the generated OTLP trace/logs/metrics export response classes corresponding to the request path to serialize empty success and partial success bytes.

Both response builders instantiate `request.path_config.response_message_type`. The path determines whether the response is a trace, log, or metric export response message; the caller's `ForwardingRequest.content_type` determines whether that message is serialized as protobuf bytes or protobuf JSON.

**JSON responses use OTLP protobuf JSON mapping.** *(implements "Response encoding matches the inferred request representation")*
JSON success serializes as `{}`. JSON partial success serializes the same OTLP response message shape as protobuf partial success, using lower camel case protobuf JSON field names.

Both protobuf and JSON responses include explicit `Content-Type` headers matching the serialized representation.

**Partial success has zero rejected records and an explanatory message.** *(implements "Locally dropped valid payloads return OTLP partial success")*
The response builder sets the relevant `partial_success` field with rejected count `0` and a local forwarding message. The trace response uses `rejected_spans`, the logs response uses `rejected_log_records`, and the metrics response uses `rejected_data_points`. The count remains `0` because this first pass does not parse opaque payloads into span, log, or metric counts.
