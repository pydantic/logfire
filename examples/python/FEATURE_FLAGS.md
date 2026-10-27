# Feature flags support demo

A small support API that uses typed flags, targeting, a percentage rollout, and a managed prompt
in the same request. It simulates an agent's decisions without calling an AI
provider. The default configuration stays in memory, and no telemetry is sent to Logfire.
Credential values are fake markers used to test redaction, not a recommendation to store
real credentials in feature flags. The client-supplied plan is demo data, not authorization.

From the repository root, install the development dependencies and start it:

```bash
uv sync --frozen
make demo-feature-flags
```

Open [the interactive API documentation](http://127.0.0.1:8000/docs), or make a request:

```bash
curl -s http://127.0.0.1:8000/support \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"example-account","plan":"team","topic":"installation"}'
```

A team request gets assistance, the `large` model, three documents, and a 256-token reply
budget. A free request does not get assistance. Each customer keeps the same compact or
detailed layout on repeated requests. The prompt reads `Help Acme customers with installation.`

The request yields to other tasks and evaluates a flag in a worker thread to exercise
context propagation. Flags cover boolean, string, integer, float, and object values, and
the API validates a Pydantic policy, a literal value, a list, and a nullable string. An undeployed emergency flag uses
its safe code default.

## Check remote delivery and failures

```bash
make test-feature-flags-demo
```

The checks run the same app over real HTTP, backed by a disposable delivery server using
the SDK's configuration and server-sent event endpoints. They cover:

- Concurrent requests with stable assignments and no per-evaluation configuration fetches.
- Scheduled revalidation alongside concurrent requests after cold-start recovery.
- Changed policies and composed prompts arriving without an explicit refresh.
- Conditional HTTP requests returning `304 Not Modified` for unchanged configuration.
- Invalid values falling back to code defaults, and malformed configuration retaining the last loaded snapshot.
- An unavailable configuration service at startup, later outages, and recovery.
- A disconnected event stream reconciling a missed update on reconnect.
- Deleted flags returning defaults with `flag_not_found`, accurate request metrics, and clean shutdown.
- One-time declarations and telemetry that omits customer identifiers and credential values.

Only the delivery boundary is fake; flag evaluation, HTTP clients, event streaming, request
handling, tracing, and metrics use their real implementations. These checks do not prove
compatibility with the hosted Logfire service or a particular production workload.

Flag telemetry records the targeting key as `feature_flag.context.id`, but not the attributes
passed for targeting. Managed-template telemetry records both, so this demo uses a non-personal
service-level key for its shared prompt. It also disables capturing FastAPI endpoint arguments. Do not copy customer identities or credentials into application logs.

The subprocesses and temporary servers stop after verification. Run `make test-feature-flags`
for the broader unit, property, lifecycle, and demo suite.
