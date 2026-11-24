# Coverage Expansion Map

Read this only after one representative service has sent verified fresh data.
Expand one source at a time and verify each before starting the next.

## Product surfaces

| Product surface | Telemetry required | Typical implementation |
|---|---|---|
| Live, Explore, Issues | Application spans, logs, exceptions | SDK configuration, framework instrumentation, structured logging |
| Services | Spans with stable service identity | `service.name`, version and environment where known |
| Metrics, dashboards, alerts | Counters, histograms and gauges | SDK metrics or the OpenTelemetry Metrics API |
| AI and LLM views | Model, agent and tool spans | Instrument the agent framework as well as the model provider |
| Hosts, Docker, Kubernetes | Infrastructure resource metrics | Use the separate `logfire-infrastructure` skill |

## Service metadata

Set resource attributes once at SDK configuration or through
`OTEL_RESOURCE_ATTRIBUTES`:

- `service.name`: stable service identity; never leave it as `unknown_service`.
- `service.version`: release/build identity when the repository defines one.
- `deployment.environment.name`: explicit dev/staging/prod identity; do not guess.
- `service.instance.id`: replica identity when the runtime already exposes one.

## Custom metrics

Add metrics only for a concrete operational question. Counters describe totals,
histograms describe distributions such as latency, and gauges describe current
state. Avoid unbounded labels such as user IDs or request URLs.

- See the [Python metric patterns](./python/logging-patterns.md).
- Rust provides counter, histogram and gauge instruments in the `logfire` crate.
- JavaScript uses the OpenTelemetry Metrics API; `@pydantic/logfire-node` does
  not provide a separate custom-metrics wrapper.

## Agent and model frameworks

Instrument the framework, not only the underlying provider, when tool calls and
agent-run boundaries matter. Pydantic AI, OpenAI Agents SDK and Claude Agent SDK
have dedicated Logfire instrumentors. LangChain/LangGraph and Google ADK expose
native OpenTelemetry; other frameworks may require an OpenInference instrumentor.
Coverage of messages, tools, tokens and cost differs by framework, so verify the
fields that actually arrived rather than assuming parity.

For JavaScript Vercel AI SDK calls, use the [AI SDK reference](./javascript/ai-sdk.md). For
Python framework calls and package requirements, use the [AI/LLM integrations reference](./python/integrations.md#aillm-frameworks).

## Expansion order

1. Add structured application logs and exception reporting.
2. Add outbound HTTP and database instrumentation actually used by the service.
3. Add agent/model instrumentation with an explicit content-capture decision.
4. Add low-cardinality custom metrics tied to operational questions.
5. Use `logfire-infrastructure` for hosts, containers, clusters and infrastructure services.

After each step, exercise a specific operation and query for fresh matching data.
