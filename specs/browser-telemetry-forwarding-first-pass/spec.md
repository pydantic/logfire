# OTLP Telemetry Forwarding First Pass

**Code-level architecture is in [code-spec](code-spec.md).**

**OTLP telemetry forwarding must not make application request handling depend on Logfire availability.**
When an external client sends OTLP telemetry through a Python backend, a Logfire outage, timeout, or retryable Logfire error must not occupy the app-serving request path until Logfire responds. Logfire telemetry may be lost, delayed, or degraded, but it must not take down unrelated app traffic.

**This first pass keeps the existing helper API and changes the implementation behind it.** *(from "OTLP telemetry forwarding must not make application request handling depend on Logfire availability")*
The existing experimental `forward_export_request` and `logfire_proxy` helpers remain the user-facing API for this pass. The spec therefore does not define a new public API from scratch; it defines the preserved behavior, changed internals, and changed response semantics of those helpers.

**Part 1: Existing Behavior We Preserve**
These requirements capture behavior the first pass keeps so implementation work can focus on the forwarding internals.

**The existing path input remains the path source.** *(from "This first pass keeps the existing helper API and changes the implementation behind it")*
The low-level helper still receives a path value, and the ASGI helper still obtains the path from the existing route/path handling. Values containing `://`, `?`, or `#` are rejected with 400. Otherwise the helper prepends a leading slash if absent, percent-decodes the path, and applies POSIX path normalization before validation.

**Only `/v1/traces`, `/v1/logs`, and `/v1/metrics` are forwarded.** *(from "The existing path input remains the path source")*
Normalized paths other than `/v1/traces`, `/v1/logs`, and `/v1/metrics` are rejected with 400 before any destination URL is constructed.

**The default request body size limit remains 50 MiB.** *(from "This first pass keeps the existing helper API and changes the implementation behind it")*
The existing ASGI helper default remains 50 MiB, and direct `forward_export_request()` calls use the same default limit. Payloads above the applicable request body size limit return 413 and are not enqueued. If the ASGI helper is called with an explicit `max_body_size`, that configured value remains the limit for the request it delegates.

**The current User-Agent composition is preserved.** *(from "This first pass keeps the existing helper API and changes the implementation behind it")*
`User-Agent` is not forwarded as a raw client-supplied header. The helper constructs its own `User-Agent`; if the incoming request has a user agent, the constructed value prefixes it with the Logfire forwarding user agent, preserving the existing behavior of identifying forwarding traffic while retaining the original user agent for context.

**Requests with no active forwarding destination are rejected with 403.** *(from "This first pass keeps the existing helper API and changes the implementation behind it")*
Forwarding destinations are created only when the selected Logfire configuration is actively sending to Logfire. If `send_to_logfire=False`, or if the selected configuration otherwise resolves zero write tokens for Logfire export, the forwarding helper cannot construct server-side Logfire authorization and returns a forbidden response rather than accepting the payload.

**Part 2: Behavior We Change**
These are the main implementation and semantic changes.

**The forwarding endpoint is an ingress adapter, not a transparent HTTP proxy.** *(from "OTLP telemetry forwarding must not make application request handling depend on Logfire availability")*
The endpoint accepts client-supplied OTLP export payloads into a local forwarding pipeline. It may validate, reject, enqueue, drop, or locally acknowledge payloads without waiting for Logfire. It is not required to preserve arbitrary incoming request semantics.

**Accepted OTLP payloads are queued locally before any Logfire network I/O.** *(from "OTLP telemetry forwarding must not make application request handling depend on Logfire availability", "The forwarding endpoint is an ingress adapter")*
The app request path must not attempt to send the payload to Logfire synchronously. Once the request has passed admission checks, the helper submits it to a local queue and returns a response based on local admission, not on remote Logfire delivery.

**Local queueing uses memory first.** *(from "Accepted OTLP payloads are queued locally before any Logfire network I/O")*
The first pass uses an in-memory queue as the primary healthy path, so healthy forwarded telemetry is not written to disk before export.

Context: normal healthy Logfire telemetry is buffered in memory by OpenTelemetry processors before export. Writing every healthy forwarded payload to disk would make forwarded telemetry worse than normal telemetry during healthy operation.

**Each backend-URL memory queue has a hardcoded 64 MiB byte limit.** *(from "OTLP telemetry forwarding must not make application request handling depend on Logfire availability", "Local queueing uses memory first")*
The first pass caps each destination memory queue at 64 MiB, defined as `64 * 1024 * 1024` queued body bytes. The limit is hardcoded rather than user-configurable, so queue capacity remains lifecycle configuration owned by Logfire internals rather than a per-request knob.

**Destination pipelines are separated by resolved backend URL.** *(from "OTLP telemetry forwarding must not make application request handling depend on Logfire availability")*
Each resolved Logfire backend URL that is active for normal Logfire export gets its own forwarding pipeline. The pipeline owns the memory queue, worker, OTLP session, and disk retry state for that backend URL. Tokens that resolve to the same backend URL are delivery targets inside the same pipeline, not separate queue or retry lifecycles.

Context: a single Logfire configuration can contain multiple tokens, and tokens can imply different backend URLs. One unhealthy backend must not hold up sends to another backend.

**Forwarding uses every active Logfire export write token grouped by backend URL.** *(from "Destination pipelines are separated by resolved backend URL")*
The first pass fans out accepted OTLP payloads to every write token that the selected configuration uses for normal Logfire export, matching the intent of a multi-token Logfire configuration. Tokens that resolve to the same backend URL share that URL's destination pipeline. The helper must not silently use only the first token.

**A full backend-URL queue does not block other backend URLs.** *(from "Destination pipelines are separated by resolved backend URL", "Each backend-URL memory queue has a hardcoded 64 MiB byte limit")*
If one backend-URL memory queue is full, forwarding still enqueues the payload to any other active backend-URL queues with capacity. The full backend URL is treated as a local drop for every active Logfire export write token that resolves to that URL.

**Forwarding sends use the existing OTLP session retry ownership.** *(from "Local queueing uses memory first")*
Background forwarding sends use `OTLPExporterHttpSession` and its existing failed-send ownership instead of creating a new forwarding retry system. The memory worker adds no queue-level sleep or backoff between send attempts.

Context: `OTLPExporterHttpSession` already retries once and then adds failed requests to `DiskRetryer`; adding another retry loop in the memory queue would duplicate existing retry ownership.

**Forwarding worker send failures are contained.** *(from "Forwarding sends use the existing OTLP session retry ownership")*
If `OTLPExporterHttpSession.post()` raises after performing its retry or disk-retry handoff, the forwarding worker treats that as a completed immediate send attempt for memory-queue lifecycle purposes. The worker logs or suppresses the exception locally, continues with any remaining token sends for the queued item, continues draining later queued items, and must not leave flush or shutdown waiting on stale active-send state.

**Forwarding send timeout follows OTLP HTTP exporter timeout configuration.** *(from "Forwarding sends use the existing OTLP session retry ownership")*
Each immediate forwarding send passes an explicit request timeout resolved with the same signal-specific precedence as the OpenTelemetry OTLP HTTP exporters. `/v1/traces` uses `OTEL_EXPORTER_OTLP_TRACES_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the OTLP exporter default. `/v1/logs` uses `OTEL_EXPORTER_OTLP_LOGS_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the OTLP exporter default. `/v1/metrics` uses `OTEL_EXPORTER_OTLP_METRICS_TIMEOUT`, then `OTEL_EXPORTER_OTLP_TIMEOUT`, then the OTLP exporter default.

Context: the OpenTelemetry Python OTLP HTTP exporters currently default this timeout to 10 seconds. Forwarding should reuse that default rather than introducing a forwarding-specific constant.

Implementation note: the path-specific timeout environment variable and default belong to centralized forwarding path metadata, alongside the path-specific OTLP response message and partial-success rejected-count field. The design does not require a standalone timeout-only path helper.

**Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call.** *(from "Accepted OTLP payloads are queued locally before any Logfire network I/O", "Forwarding sends use the existing OTLP session retry ownership")*
Public forwarding functions must not create independent long-lived queues, sessions, or disk retryers per request. They submit work to forwarding lifecycle owned by the relevant `LogfireConfig`.

Context: closing an `OTLPExporterHttpSession` can close its `DiskRetryer`, which drops pending disk retry tasks. Therefore sessions created for forwarding must be long-lived and must not be closed simply because a memory queue becomes empty.

**Forwarding participates in Logfire flush and shutdown.** *(from "Forwarding transport lifecycle is owned by Logfire configuration", "Local queueing uses memory first")*
`logfire.force_flush()` and `logfire.shutdown()` include the forwarding memory queues owned by the same configuration. Flush waits for each forwarding worker to finish its current queue, up to the available timeout. Shutdown stops accepting new forwarding items and, with `flush=True`, waits for each forwarding worker to finish within the timeout. If the timeout expires first, shutdown drops queued memory work, leaves final session close to worker cleanup, and reports incomplete. The caller's timeout is a shared overall deadline across forwarding workers owned by the configuration.

When `logfire.shutdown(flush=False)` is used, forwarding shutdown still runs because forwarding owns non-daemon workers and long-lived sessions. In this mode shutdown closes admission, drops memory-queued forwarding work, waits for any live worker to finish within the timeout, closes forwarding-owned sessions, and returns without treating the intentional queued-work drop as a forwarding drain timeout. It must not use `flush=False` as a reason to leave forwarding admission state alive.

**The forwarding worker is non-daemon and lifecycle-managed.** *(from "Forwarding participates in Logfire flush and shutdown")*
The worker is controlled by flush/shutdown rather than abandoned at interpreter exit. The worker may exit after draining current memory work and be recreated later, but the destination session and any disk retry state remain owned by the configuration-level forwarding manager until real shutdown or reconfiguration. During shutdown, the manager waits for live workers within the caller timeout and reports incomplete if the timeout expires first.

**Post-shutdown forwarding calls are locally dropped.** *(from "Forwarding participates in Logfire flush and shutdown", "The forwarding endpoint is an ingress adapter")*
If a request is otherwise valid but arrives after forwarding shutdown has closed admission, the helper returns HTTP 200 with an OTLP partial-success response in the request representation. It must not recreate forwarding queues after shutdown.

**The helper forwards only whitelisted representation headers.** *(from "The forwarding endpoint is an ingress adapter")*
The only client-supplied headers used for the Logfire-bound representation are `Content-Type` and `Content-Encoding`, looked up case-insensitively. This is a closed whitelist, not a blacklist of known-unsafe headers. The helper must not forward arbitrary incoming request headers; any future forwarded client-supplied header must be added deliberately.

**Server authentication headers are injected, not forwarded from the client.** *(from "The helper forwards only whitelisted representation headers")*
Client-supplied `Authorization`, `Cookie`, `Host`, hop-by-hop headers, proxy headers, forwarding headers, and custom credential-like headers must not be sent to Logfire. The forwarding pipeline constructs Logfire authorization from the active Logfire export write tokens.

**The first pass supports protobuf and JSON OTLP payload representations.**
Forwarding accepts the two OTLP HTTP payload representations needed for client exporters in this pass: protobuf and JSON.

**`Content-Type` supports protobuf and JSON OTLP.** *(from "The helper forwards only whitelisted representation headers", "The first pass supports protobuf and JSON OTLP payload representations")*
The helper infers the local OTLP response representation by looking for `application/x-protobuf` or `application/json` in the `Content-Type` header value case-insensitively. It does not validate the header as a media type; the Logfire backend remains responsible for accepting or rejecting the forwarded header semantics. Missing `Content-Type` or a value that contains neither supported representation marker is rejected with 415 rather than blindly forwarded.

Because forwarded payloads are opaque, the Logfire-bound `Content-Type` header preserves the original inbound `Content-Type` field value. The inferred representation controls only the local success or partial-success response encoding; it does not rewrite the body or its representation metadata.

**Response encoding matches the inferred request representation.** *(from "`Content-Type` supports protobuf and JSON OTLP", "The forwarding endpoint is an ingress adapter")*
Protobuf requests receive protobuf OTLP success or partial-success responses. JSON requests receive JSON OTLP success or partial-success responses. The helper must not accept JSON and return protobuf.

Context: an empty successful OTLP JSON response is `{}`. A partial-success JSON response uses the OTLP protobuf JSON mapping, for example `{"partialSuccess": {"errorMessage": "..."}}`.

**Accepted queued payloads return local OTLP success.** *(from "Accepted OTLP payloads are queued locally before any Logfire network I/O", "Response encoding matches the inferred request representation")*
If a valid payload is accepted into the local memory queue for every configured backend URL, the helper returns HTTP 200 with an empty OTLP export response in the request representation. This response means local admission succeeded, not that Logfire has received the payload.

**Locally dropped valid payloads return OTLP partial success.** *(from "The forwarding endpoint is an ingress adapter", "Response encoding matches the inferred request representation", "A full backend-URL queue does not block other backend URLs")*
If a payload passes request validation but cannot be accepted for one or more configured backend URLs, the helper returns HTTP 200 with an OTLP partial-success response in the request representation. This includes post-shutdown admission closure, one or more backend-URL queues exceeding the 64 MiB limit, and other local queue-unavailable cases.

**Documentation of externally driven ingress is deferred to the docs source repo.** *(from "The forwarding endpoint is an ingress adapter")*
External clients can be numerous, retrying, duplicated, or malicious. Documentation must tell users to protect the endpoint with their normal auth/session/CORS/rate-limiting controls, but the browser integration markdown page has moved out of this repository. The deferred docs work should port the intent captured in `ignoreme/workflow/patches/pr-1940-browser.patch` to the repository that now owns that page.

**CORS documentation is deferred with the ingress documentation.** *(from "Documentation of externally driven ingress is deferred to the docs source repo")*
The deferred docs update should say CORS should match the app origin, not `*`, unless the user intentionally wants public telemetry ingestion using their backend's Logfire write authority.

**Part 3: Scope Exclusions**
These are explicit non-goals for this pass.

**The first pass has no separate memory-queue item limit.**
The memory queue is capped by queued body bytes only. Request body size limits still apply before enqueueing.

**The first pass does not parse, split, merge, or rewrite OTLP payloads.**
The helper treats traces, logs, and metrics payloads as opaque bytes after validating route, content type, and size. It does not merge small requests, split large requests, rewrite resources, or apply span/log/metric processors.

**Python scrubbing rules do not apply to opaque forwarded payloads.** *(from "The first pass does not parse, split, merge, or rewrite OTLP payloads")*
Because the first pass does not parse the OTLP payload, Python-side Logfire scrubbing cannot redact forwarded telemetry attributes. The deferred browser docs update must make clear that forwarded telemetry should be scrubbed before it reaches the forwarding endpoint.

**Forwarding flush and shutdown do not wait for DiskRetryer recovery.**
The first pass only needs forwarding flush/shutdown to cover the memory queue and the immediate `OTLPExporterHttpSession.post()` calls made by forwarding workers. If the OTLP session hands a failed request to `DiskRetryer`, flush and shutdown do not wait for later disk retry recovery.

Context: existing normal export force flush does not guarantee eventual success for payloads already handed to `DiskRetryer`.

**Forwarding-specific counters are not part of the first-pass scope.**
Accepted/dropped/queued counters may be useful later, but OTLP forwarding does not inherently require them more than normal exports. They are optional polish, not a first-pass design constraint.

**The first pass does not honor arbitrary OTLP environment variables for forwarding transport.**
Forwarding follows the Logfire instance/config destination and token model. Generic OTLP exporter environment variables must not redirect forwarded payloads or override Logfire authorization unless a future spec explicitly adds that behavior. Timeout environment variables are the narrow exception defined by "Forwarding send timeout follows OTLP HTTP exporter timeout configuration"; this exception does not extend to OTLP endpoint, header, compression, certificate, or credential-provider environment variables.

**Implementation must update this spec before adding behavior outside it.**
If implementation reveals that a queue limit, response code, timeout, shutdown detail, or API shape is necessary but not specified here, the spec must be updated before or alongside the code. This keeps the first pass reviewable against the design rather than against conversation memory.
