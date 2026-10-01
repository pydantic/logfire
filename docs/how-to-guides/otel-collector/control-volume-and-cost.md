---
title: "Control volume and cost"
description: "Drop the telemetry you never look at and keep the traces that matter, using the OpenTelemetry Collector's filter and tail sampling processors."
---
# Control volume and cost

Cut what you send to Logfire without losing what you debug with. Doing this in the Collector means one set of rules for every service, changed without a redeploy.

Three levers, in the order worth trying them:

1. **Drop what you never look at.** Health checks, readiness probes, and static asset requests. The safest lever, as long as you restrict it to requests that are a whole trace on their own.
2. **Sample the rest.** Keep every error and every slow request, keep a fraction of the ordinary ones.
3. **Trim metrics.** Collection interval and cardinality, which is the number of separate series you produce.

## Before you start

You need a Collector already forwarding to Logfire. If you do not have one, start with [Send data through a Collector](send-data-through-a-collector.md). You also need the `contrib` build, `otel/opentelemetry-collector-contrib`: both processors on this page are missing from the core build, and a Collector that does not have them refuses to start.

The configurations below are additions to that base, not whole files. Each one shows the
`processors` and `service` sections that change; keep your existing `receivers` and `exporters`.
They are also cumulative: the sampling example keeps the `filter/noise` processor the first one
defines, so apply them in order rather than on their own.

Measure first. Without a number to compare against, you cannot tell whether a change helped. The **Usage** tab in your organization's billing settings shows what you are currently sending.

## Drop traffic you never look at

The `filter` processor removes spans (one unit of work: a single operation, with a name, a start, and a duration) that match a condition, before anything else sees them:

```yaml title="otel-collector-config.yaml"
processors:
  filter/noise:
    error_mode: ignore
    traces:
      span:
        - 'attributes["url.path"] == "/health"'
        - 'attributes["url.path"] == "/ready"'
        - 'IsMatch(attributes["url.path"], "^/static/")'

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [filter/noise, batch]
      exporters: [otlphttp]
```

`error_mode: ignore` keeps a span flowing when the attribute it names is absent, rather than failing the batch.

This is the bluntest lever and the safest one, because health checks are almost always a single span with no children. Be careful applying it to spans in the middle of a trace (the full journey of one request, made of nested spans): removing a parent leaves its children with no parent, and the trace renders with gaps.

## Keep the interesting traces and sample the rest

Sampling keeps a representative subset of traces to control cost and volume; traces that are not kept are never sent. Head sampling makes that decision at the start of a request, before you know whether it failed. Tail sampling waits for the whole trace, so it can keep every error and every slow request and throw away only the ordinary ones.

```yaml title="otel-collector-config.yaml"
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 100000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1000
      - name: sample-the-rest
        type: probabilistic
        probabilistic:
          sampling_percentage: 10

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [filter/noise, tail_sampling, batch]
      exporters: [otlphttp]
```

Policies are evaluated together, and a trace is kept when any one of them says keep. So this configuration keeps every request your instrumentation marked as an error, every request slower than one second, and 10% of everything else.

That first category is narrower than "every failure". `status_code` matches spans whose OpenTelemetry status is `ERROR`, which most instrumentations do not set for a 4xx response, for a handler that catches an exception and returns a 200, or for a model that answers quickly and wrongly. Those are judged by the remaining policies: a slow one is still caught by `keep-slow`, and a fast one falls to the 10% bucket with ordinary traffic. If a class of failure matters to you, give it a policy of its own rather than assuming this one covers it.

Tail sampling can only keep what reaches it. If the application or an upstream Collector already dropped a trace through head sampling, no policy here can bring it back, so leave head sampling at 100% on the traffic you want these policies to judge.

`decision_wait: 10s` is how long the Collector holds a trace before deciding. It must be longer than your slowest trace, or long traces are judged on the spans that arrived in time. `num_traces` is how many traces it holds in memory while waiting, so raising `decision_wait` or your traffic raises memory use.

!!! warning
    Tail sampling needs every span of a trace to reach the same Collector instance. With more than one Collector behind a load balancer, spans of one trace land on different instances and each sees a partial trace. Running a layer of Collectors that route by trace ID (the `loadbalancing` exporter) in front of the sampling layer is the usual fix.

### What sampling costs you

Anything counted from spans is counted from the spans you kept, so absolute numbers undercount. "How many requests did we serve" is wrong after sampling; "what is the p99 latency of the slow ones" is still right, because the slow ones are all kept.

The loss you feel first is different, and worth being ready for: a customer reports a problem, you go to find their request, and nine times in ten it was not kept. Sampling trades the ability to answer "what happened to this one request" for a smaller bill. Keep the error and latency policies generous if that trade worries you.

If you need exact request counts, record them as [metrics](../../guides/onboarding-checklist/add-metrics.md) rather than counting spans. Metrics are aggregated before they leave your application, so sampling does not change them.

## Trim metric volume

Interval and cardinality both multiply.

**Interval.** Moving a receiver from 10 seconds to 60 seconds sends one sixth as many datapoints. One minute is enough resolution for infrastructure trends, and several deployment presets default to 10 seconds. Do not shorten receivers that already default to longer.

**Cardinality.** Every distinct combination of attributes is its own series. Watch for dimensions that multiply per process, container, pod, CPU core, disk, filesystem, or network interface. The [host monitoring guide](host-monitoring.md#cardinality-and-cost) explains why the per-process scraper normally stays off, and the [Kubernetes volume guide](kubernetes-reduce-volume.md) gives a lower-volume configuration that keeps the Kubernetes page working.

Enable only the metrics and attributes you actually query.

## Verify the reduction

Restart the Collector and watch two things.

The Collector reports its own counters at `http://localhost:8888/metrics`.

In Docker, publishing the port is not enough. The listener binds inside the container, so you have to move it to `0.0.0.0` as well, then publish it:

```yaml title="otel-collector-config.yaml"
service:
  telemetry:
    metrics:
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888
```

Add `-p 8888:8888` to the `docker run` command alongside that. With only the published port and no `host` override, the request below is refused. Compare what came in against what went out. The gap is mostly what filtering and sampling removed, but failed exports and full queues land in it too, so check `otelcol_exporter_send_failed_spans` before reading the whole gap as a successful reduction.

```bash
curl -s http://localhost:8888/metrics | grep -E 'otelcol_(receiver_accepted|exporter_sent)_spans'
```

The two numbers are cumulative totals since the Collector started:

```
otelcol_receiver_accepted_spans{receiver="otlp",...} 1842
otelcol_exporter_sent_spans{exporter="otlphttp",...} 231
```

Here the Collector took in 1,842 spans and forwarded 231, so filtering and sampling removed
about 87% of them.

Then compare the **Usage** tab against the number you wrote down before the change. Give it a full day, since traffic varies by hour.

## Troubleshoot volume changes

**Traces arrive with gaps in them.** A `filter` rule is removing spans from the middle of a trace. Restrict the rule to spans with no parent, or move the decision into `tail_sampling`, which keeps or drops whole traces.

**Sampling keeps far more than the percentage suggests.** A trace is kept when any policy matches. If most of your traffic is erroring or slow, the `keep-errors` and `keep-slow` policies are doing exactly what you asked. Check the error rate before lowering the probabilistic percentage.

**Memory climbs after enabling tail sampling.** The Collector holds every in-flight trace for `decision_wait`. Shorten `decision_wait` or give the Collector more memory, and add the `memory_limiter` processor first in the pipeline to make the ceiling explicit. Lower `num_traces` only as a last resort: it is a hard cap on traces held in memory, and traces evicted when it is reached are dropped before any policy judges them, so errors and slow requests stop being kept.

**Traces look incomplete only since enabling tail sampling.** More than one Collector instance is receiving spans from one trace. See the warning above.

## Next steps

- [Scrub sensitive data](otel-collector-scrubbing.md) in the same pipeline.
- [Sampling in the SDK](../sampling.md) when you would rather decide in the application.
