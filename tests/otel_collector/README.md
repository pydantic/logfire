# OpenTelemetry Collector conformance tests

These tests exercise Logfire's OpenTelemetry Protocol (OTLP) HTTP transport against a real,
digest-pinned OpenTelemetry Collector. They are separate from the default test run because they
require Docker:

```bash
make test-otel-collector
```

The harness uses this path for HTTP traffic:

```text
Logfire SDK -> stable local gateway -> OpenTelemetry Collector -> protobuf capture server
```

The gateway keeps the software development kit (SDK) endpoint stable while a test destroys and
recreates the Collector. The capture server parses the exported protobuf messages and lets tests
reconcile uniquely identified traces, metric points, and log records. HTTPS goes directly to a
second Collector receiver using a fresh, explicitly trusted test certificate.

Programmable local proxies cover transport failures that stopping the Collector cannot model:
silently orphaned pooled connections, retryable and terminal HTTP responses, lost response
acknowledgements, ordinary forward-proxy traffic, and HTTPS tunnels created with `CONNECT`.

The Collector exporter's queue and retry behavior are disabled. This keeps the Collector from
hiding whether the SDK retried a request.

## Delivery contract

The tests distinguish these outcomes:

- A request that cannot reach the stopped Collector must be replayed from the SDK's disk queue.
  Every identified record must arrive exactly once after the replacement Collector is healthy.
- If the Collector accepts a request but its acknowledgement is lost, the SDK retries the same
  request. Every record must arrive, but duplicate delivery is expected because OTLP does not
  provide exactly-once acknowledgement semantics.
- Retryable status codes must make a second attempt. Terminal client errors must not loop.
- The disk queue is process-local scratch space, not durable storage. Closing the session discards
  pending retries; a fast exporter characterization test outside this Docker suite makes that
  boundary explicit.

## Connection policy contract

- A silently orphaned direct, forward-proxy, or HTTPS tunnel connection must be recycled before
  reuse once its idle window expires. The direct, forward-proxy, and HTTPS `CONNECT` regression
  cases first prove that an ordinary `requests` session stalls against the same fault.
- The separate disk-retry session must use the same recycling policy as the main exporter session.
- A fast companion transport test verifies that a real connected socket has TCP keepalive enabled
  with every tuning option exposed by the host platform.

Collector logs, rendered configuration, the test certificate, and captured OTLP JSON are uploaded
by CI on every run. The generated private key is removed before artifact upload.
