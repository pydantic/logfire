# OTLP Telemetry Forwarding First Pass Diagrams

**These diagrams support the code spec in [code-spec](code-spec.md), which implements the prose spec in [spec](spec.md).**

**Forwarding ownership is config-scoped and backend-url separated.** *(supports "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call", "Destination pipelines are separated by resolved backend URL")*
This diagram shows ownership and isolation boundaries. Public helpers submit to the config-owned manager; the manager separates work by resolved backend URL; each backend-url pipeline owns its memory queue, worker, session, and disk retry state.

```mermaid
flowchart LR
    Proxy["logfire_proxy"] -->|"read ASGI body and path"| Helper["forward_export_request"]
    Helper --> Config["LogfireConfig._otlp_forwarding"]
    Config --> Manager["OTLPForwardingManager"]
    Manager -->|"pipeline by backend URL"| PipelineA["OTLPForwardingPipeline: backend URL A"]
    Manager -->|"pipeline by backend URL"| PipelineB["OTLPForwardingPipeline: backend URL B"]
    PipelineA --> TokensA["tokens for backend URL A"]
    PipelineB --> TokensB["tokens for backend URL B"]
    PipelineA --> QueueA["memory queue: 64 MiB"]
    PipelineB --> QueueB["memory queue: 64 MiB"]
    PipelineA --> ActiveA["active immediate send count"]
    PipelineB --> ActiveB["active immediate send count"]
    PipelineA --> WorkerA["non-daemon worker"]
    PipelineB --> WorkerB["non-daemon worker"]
    WorkerA --> SessionA["OTLPExporterHttpSession"]
    WorkerB --> SessionB["OTLPExporterHttpSession"]
    SessionA -->|"retryable failure"| RetryA["DiskRetryer"]
    SessionB -->|"retryable failure"| RetryB["DiskRetryer"]
    SessionA --> LogfireA["Logfire backend URL A"]
    SessionB --> LogfireB["Logfire backend URL B"]
```

**Request admission returns before Logfire delivery.** *(supports "Accepted OTLP payloads are queued locally before any Logfire network I/O", "Accepted queued payloads return local OTLP success", "Locally dropped valid payloads return OTLP partial success")*
This sequence shows the response boundary. Validation failures return local error responses. Valid requests are submitted to the manager, and the client response reflects local admission only. Background workers perform Logfire sends after the app request path has returned.

```mermaid
sequenceDiagram
    participant Client as External OTLP client
    participant Proxy as logfire_proxy
    participant Helper as forward_export_request
    participant Manager as OTLPForwardingManager
    participant Pipeline as OTLPForwardingPipeline
    participant Worker as pipeline worker
    participant Session as OTLPExporterHttpSession
    participant Logfire as Logfire backend

    Client->>Proxy: POST OTLP export payload
    Proxy->>Proxy: read bounded ASGI body and path
    Proxy->>Helper: forward_export_request(path, headers, body, max_body_size)
    Helper->>Helper: validate path, content type, body, token
    alt validation fails
        Helper-->>Client: 400 / 403 / 413 / 415
    else request is valid
        Helper->>Manager: submit(ForwardingRequest)
        Manager->>Pipeline: enqueue(ForwardingRequest)
        alt all backend-url queues accept
            Manager-->>Helper: ForwardingAdmissionResult: success
            Helper-->>Client: 200 empty OTLP success
        else one or more backend-url queues drop
            Manager-->>Helper: ForwardingAdmissionResult: partial_success
            Helper-->>Client: 200 OTLP partial success
        end
        Worker->>Pipeline: dequeue memory work
        Worker->>Session: post once per token
        Session->>Logfire: OTLP HTTP export
    end
```

**Forwarding data types are small and owned by one layer.** *(supports "Forwarding transport lifecycle is owned by Logfire configuration, not by each forwarding call", "Destination pipelines are separated by resolved backend URL")*
This type graph covers the data structures and stateful owners used by the forwarding path. External synchronization/transport types are included where they appear as fields because they define lifecycle responsibilities.

```mermaid
classDiagram
    class LogfireConfig {
        _otlp_forwarding: OTLPForwardingManager
    }

    class OTLPForwardingManager {
        config: LogfireConfig
        pipelines: dict
        closed: bool
        lock: RLock
        submit(request) ForwardingAdmissionResult
        has_destinations() bool
        add_destination(base_url, token)
        force_flush(timeout_millis) bool
        shutdown(timeout_millis, drain_queued) bool
    }

    class OTLPForwardingPipeline {
        base_url: str
        session: OTLPExporterHttpSession
        queue: deque
        queued_body_bytes: int
        active_send_count: int
        max_queued_body_bytes: int
        worker: Thread optional
        closed: bool
        condition: Condition
        tokens: list
        enqueue(request) bool
        force_flush(timeout_millis) bool
        shutdown(timeout_millis, drain_queued) bool
        _run()
        _send(request)
    }

    class ForwardingRequest {
        path
        body
        content_type: ForwardingContentType
        headers
        path_config
    }

    class ForwardingContentType {
        <<enumeration>>
        PROTOBUF
        JSON
    }

    class ForwardingAdmissionResult {
        response
        message
    }

    class ForwardingErrorResponse {
        status_code
        content
    }

    class ForwardingPathConfig {
        timeout_env
        default_timeout
        partial_success_rejected_attribute
        response_message_type
        timeout() float
    }

    class FORWARDING_CONFIGS {
        <<constant>>
    }

    class ForwardExportRequestResponse {
        status_code
        headers
        content
    }

    class OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES {
        <<constant>>
    }

    class OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES {
        <<constant>>
    }

    class RLock
    class Condition
    class Thread
    class deque
    class OTLPExporterHttpSession
    class DiskRetryer

    LogfireConfig *-- OTLPForwardingManager : owns
    OTLPForwardingManager --> RLock : protects manager state
    OTLPForwardingManager *-- OTLPForwardingPipeline : pipelines by base_url
    OTLPForwardingManager ..> ForwardingRequest : enqueues shared request
    OTLPForwardingManager ..> ForwardingAdmissionResult : returns
    OTLPForwardingPipeline --> OTLPExporterHttpSession : sends through
    OTLPForwardingPipeline ..> FORWARDING_CONFIGS : timeout per signal path
    FORWARDING_CONFIGS *-- ForwardingPathConfig : per path
    OTLPExporterHttpSession --> DiskRetryer : defers retryable failures
    OTLPForwardingPipeline --> Condition : protects queue state
    OTLPForwardingPipeline --> Thread : worker
    OTLPForwardingPipeline --> deque : queue storage
    OTLPForwardingPipeline --> OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES : default limit
    OTLPForwardingPipeline *-- ForwardingRequest : queues
    ForwardingRequest --> ForwardingContentType : representation
    ForwardingRequest ..> OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES : default admission limit
```

**Admission functions convert inbound HTTP into a local response.** *(supports "The forwarding endpoint is an ingress adapter, not a transparent HTTP proxy", "Response encoding matches the inferred request representation")*
This call graph covers the public helpers, validation helpers, response builders, and response/result data types. It shows where `ForwardingErrorResponse` stops the path before queue admission and where `ForwardExportRequestResponse` is produced for the caller.

```mermaid
flowchart TD
    Proxy["logfire_proxy(request)"] -->|"body limit and path extraction"| Forward["forward_export_request(path, headers, body, logfire_instance, max_body_size)"]
    Forward --> BuildRequest["build_forwarding_request(path, headers, body, max_body_size)"]
    BuildRequest --> ParseContentType["infer response representation from Content-Type marker"]
    ParseContentType --> ContentType["ForwardingContentType"]
    ParseContentType -->|"missing / empty / unsupported"| Error["ForwardingErrorResponse"]
    BuildRequest -->|"validation failure"| Error
    Error --> PublicError["ForwardExportRequestResponse"]
    BuildRequest -->|"valid"| Request["ForwardingRequest"]
    Forward --> HasDestinations["OTLPForwardingManager.has_destinations()"]
    HasDestinations -->|"false"| Error
    HasDestinations -->|"true"| Submit["OTLPForwardingManager.submit(request)"]
    Submit --> Admission["ForwardingAdmissionResult"]
    Admission -->|"response == success"| SuccessBuilder["build_success_response(request)"]
    Admission -->|"response == partial_success"| PartialBuilder["build_partial_success_response(request, message)"]
    SuccessBuilder --> ResponseMessageA["request.path_config.response_message_type"]
    PartialBuilder --> ResponseMessageB["request.path_config.response_message_type"]
    ResponseMessageA --> PublicSuccess["ForwardExportRequestResponse"]
    ResponseMessageB --> PublicPartial["ForwardExportRequestResponse"]
```

**Manager and pipeline methods own lifecycle, flushing, and sending.** *(supports "Forwarding participates in Logfire flush and shutdown", "The forwarding worker is non-daemon and lifecycle-managed", "Forwarding sends use the existing OTLP session retry ownership")*
This lifecycle graph covers each manager and pipeline method. It also shows how config-level lifecycle calls interact with the forwarding manager and how the worker uses the existing OTLP session retry behavior.

```mermaid
flowchart TD
    Configure["LogfireConfig.configure(...)"] -->|"replace lifecycle"| ManagerShutdownOld["OTLPForwardingManager.shutdown(timeout_millis)"]
    Configure --> NewManager["new empty OTLPForwardingManager"]
    NewManager --> SendToLogfire{"send_to_logfire?"}
    SendToLogfire -->|"false"| EmptyManager["no forwarding destinations"]
    SendToLogfire -->|"true"| TokenLoop["normal Logfire exporter token loop"]
    TokenLoop --> ResolveDestination["resolve base_url for token"]
    ResolveDestination --> BuildExporters["construct normal OTLP exporters"]
    ResolveDestination --> AddDestination["OTLPForwardingManager.add_destination(base_url, token)"]
    AddDestination --> PipelineForDestination["create or reuse pipeline for backend URL"]

    ConfigFlush["LogfireConfig.force_flush(timeout_millis)"] --> ManagerFlush["OTLPForwardingManager.force_flush(timeout_millis)"]
    LogfireShutdown["Logfire.shutdown(timeout_millis, flush)"] --> ManagerShutdown{"flush?"}
    ManagerShutdown -->|"true"| ManagerShutdownDrain["OTLPForwardingManager.shutdown(timeout_millis, drain_queued=True)"]
    ManagerShutdown -->|"false"| ManagerShutdownDrop["OTLPForwardingManager.shutdown(timeout_millis, drain_queued=False)"]

    HasDestinations["OTLPForwardingManager.has_destinations()"] --> Submit["OTLPForwardingManager.submit(request)"]
    Submit --> Group["pipelines by backend URL"]
    Submit --> Pipeline["OTLPForwardingPipeline"]
    Pipeline --> Enqueue["OTLPForwardingPipeline.enqueue(request)"]
    Enqueue --> Limit["OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES"]
    Enqueue --> Condition["Condition protects queue bytes, active_send_count, worker, closed"]
    Enqueue --> Worker["Thread target: OTLPForwardingPipeline._run()"]
    Worker --> ActiveSend["increment active_send_count"]
    ActiveSend --> Send["OTLPForwardingPipeline._send(request)"]
    Send --> Headers["build_forwarding_headers(request, token)"]
    Send --> Timeout["request.path_config.timeout()"]
    Timeout --> SessionPost["OTLPExporterHttpSession.post(..., timeout=timeout)"]
    Send --> SessionPost
    SessionPost -->|"retryable failure"| Retryer["DiskRetryer"]
    SessionPost -->|"exception re-raised"| ContainToken["log or suppress and continue remaining tokens"]
    ContainToken --> ClearActive["decrement active_send_count and notify"]
    SessionPost --> ClearActive
    Send -->|"unexpected exception"| ContainItem["log or suppress and continue later queued items"]
    ContainItem --> ClearActive

    ManagerFlush --> PipelineFlush["OTLPForwardingPipeline.force_flush(timeout_millis)"]
    PipelineFlush --> Condition
    PipelineFlush --> FlushWaitEmpty["wait for queue empty and active_send_count == 0"]

    ManagerShutdownDrain --> PipelineShutdown["OTLPForwardingPipeline.shutdown(timeout_millis, drain_queued=True)"]
    ManagerShutdownDrop --> PipelineShutdownNoDrain["OTLPForwardingPipeline.shutdown(timeout_millis, drain_queued=False)"]
    ManagerShutdownOld --> PipelineShutdown
    PipelineShutdown --> Condition
    PipelineShutdown --> ShutdownDrain["drain queued memory until empty or timeout"]
    ShutdownDrain -->|"timeout with queued work"| DropQueued["drop unsent queued memory work"]
    ShutdownDrain --> WaitActive["wait for active_send_count == 0"]
    DropQueued --> WaitActive
    PipelineShutdownNoDrain --> DropQueuedNoDrain["drop unsent queued memory work without drain attempt"]
    DropQueuedNoDrain --> WaitActive
    WaitActive --> SessionClose["OTLPExporterHttpSession.close()"]
    Retryer -.->|"not awaited by flush/shutdown"| SessionClose
```
