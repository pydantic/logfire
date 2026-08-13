---
title: "Ingest limits: request size, timestamps, and attribute sizes"
description: "The limits Logfire applies to data you send: 100 MB per request, timestamps from 24 hours in the past to 1 hour in the future, and 10 MB of attributes per record."
---

# Ingest limits

Find out why a batch was refused, why a value came back shortened, and what to change so the next one lands intact.

Logfire receives data over the OpenTelemetry Protocol (OTLP, the standard wire format Logfire uses to receive telemetry). One request carries many records, where a record is a single span (one unit of work, with a name, a start, and a duration), a log (a timestamped record of one event), or a metric data point (one reading of a number tracked over time). Every request is checked against a few fixed limits before anything is stored, and there are two possible outcomes:

- **Rejected**: the data is not stored. This happens to requests that are too large, and to individual records whose timestamps fall outside the accepted window.
- **Truncated**: the record is stored, but an oversized value is shortened. Attributes and long text fields are always truncated, never rejected.

These limits are the same in the [US and EU regions](data-regions.md) and are not configurable per project.

## At a glance

| What | Limit | What happens past it |
| --- | --- | --- |
| Request body | 100 MB | Request rejected, `413 Payload Too Large`, nothing stored |
| Timestamp in the past | 24 hours | Record dropped, the rest of the request is stored |
| Timestamp in the future | 1 hour | Record dropped, the rest of the request is stored |
| Attributes per record | 10 MB | Attributes truncated, record stored |
| A log's `body` field | 10 MB | Body truncated, record stored |
| Message, span name, event name, service name, and similar short fields | 512 bytes | Value truncated, record stored |
| Exception message, exception type, stack trace, OpenTelemetry status message | 32,000 bytes | Value truncated, record stored |

## Request size

A single request to `/v1/traces`, `/v1/logs`, or `/v1/metrics` can carry at most 100 MB (104,857,600 bytes). The limit is applied twice, once to the bytes on the wire and once after decompression, so compressing a batch does not let you send a larger one.

A request over the limit is answered `413 Payload Too Large` and none of it is stored. OTLP clients treat `413` as permanent and drop the batch instead of retrying, so this is lost data, not delayed data.

Normal SDK setups stay far below 100 MB, because OpenTelemetry batch exporters flush on a size and time schedule. You reach it by putting very large values on many records at once: whole request and response bodies, base64 file contents, or large model prompts on every span in a batch. If you hit it, lower your exporter's batch size (`OTEL_BSP_MAX_EXPORT_BATCH_SIZE` for OpenTelemetry SDKs) or stop attaching the large value.

## Timestamps

Logfire accepts timestamps from **24 hours in the past** to **1 hour in the future**, measured against Logfire's own clock at the moment the request arrives, not against the clock of the machine that sent it.

Which timestamps are checked depends on the signal:

| Signal | Timestamps checked |
| --- | --- |
| Spans | The span's start time, its end time, and the timestamp of every span event |
| Logs | `time_unix_nano`, or `observed_time_unix_nano` when `time_unix_nano` is unset |
| Metric data points | The point's own timestamp against both bounds. Its start time is checked against the future bound only, because a start time is often when the process booted and is legitimately old. |

### What happens to data outside the window

Rejection is per record, not per request. Logfire drops the records that fall outside the window, stores everything else, and answers `200` with an OTLP partial success that says how many records it dropped and why:

```text
service_name=my-api -> scope_name=my.tracer -> span_name=GET /orders -> start_timestamp: dropped 37 spans whose timestamps fall outside the accepted range: got 2026-08-11 09:12:44.512 UTC but the oldest timestamp accepted is 2026-08-12 09:14:01.004 UTC. This usually means the clock on the sending host is wrong, or the data was buffered and exported long after it was recorded.
```

Most exporters do not surface a partial success anywhere you will see it, so Logfire also writes one record into your project carrying the same explanation. Look for a span named `logfire ingest error` at error level under the service name `logfire-ingest`. Its message is the text above, and a `location` attribute repeats where in your payload the first rejected record sat.

If **every** record in the request falls outside the window there is nothing left to store, and the request is answered `422 Unprocessable Entity` with the same explanation as a JSON body.

### Why timestamps end up outside the window

- **The sending host's clock is wrong.** A virtual machine or container whose clock has drifted stamps every span with the wrong time. Run a time sync daemon (`chronyd`, `systemd-timesyncd`) on the host.
- **Data was buffered offline and exported much later.** A mobile client, a batch job, or an OpenTelemetry Collector that retried for a day sends records whose timestamps are now older than 24 hours.
- **You are backfilling historical data.** Loading records older than 24 hours is not supported. Logfire is a live telemetry backend, and the 24-hour bound is what lets it decide when a slice of time is settled.

## Attribute and message size

Attributes are the key/value data you attach to a record. All the attributes on one record share a budget of **10 MB**, counting the key names and the JSON-encoded values together.

A record inside the budget is stored exactly as you sent it. A record over the budget is cut down in stages, stopping as soon as it fits:

1. Shorten every string longer than 32,000 bytes.
2. Cap containers at any nesting depth: arrays keep their first 64 entries, objects keep their first 1024 keys.
3. Drop the largest remaining values, one at a time, until the record fits.

!!! note "Those three numbers are not limits on what you can send"
    The 32,000-byte, 64-entry, and 1024-key figures only describe the order in which an over-budget record is cut down. A span carrying one 100,000-byte string and nothing else is under 10 MB, so none of these steps run and the string is stored whole.

Truncated strings keep their beginning and end with `...` in the middle, so a shortened value stays recognizable.

A log's `body` field has its own separate 10 MB budget and is truncated the same way.

### Seeing what was truncated

Every attribute path that was shortened or dropped is recorded in a `logfire.truncated` attribute on the record. In the Live view, open the record: a **Truncation** panel lists the attributes that were cut, so you can tell a truncated value from one your code never set.

## Fields with a fixed length

A few fields are always truncated at a fixed length, whatever the size of the rest of the record. Truncation here is silent: these fields are not listed in `logfire.truncated`.

**512 bytes:**

- The message shown in the Live view (`logfire.msg`, falling back to the span name)
- Span name and span event name
- `service.name`, `service.namespace`, `service.version`, `service.instance.id`
- `deployment.environment`
- Scope name and scope version
- `telemetry.sdk.name`, `telemetry.sdk.language`, `telemetry.sdk.version`
- Trace ID, parent span ID, span kind, and OpenTelemetry status code
- Metric name, type, unit, description, and aggregation temporality

**32,000 bytes:**

- `exception.message`, `exception.type`, and `exception.stacktrace`
- The OpenTelemetry status message

The message field is the one that surprises people. Logfire builds it from `logfire.msg` when that attribute is present and from the span name otherwise, stores 512 bytes of it, and does not keep the original text anywhere else. If you need the full text searchable, put it in an attribute of its own as well.

## Data Logfire cannot store

A few OTLP shapes are refused whatever their size. Each one drops a single data point or metric, and reports itself the same way an out-of-range timestamp does: partial success on the response, plus a `logfire ingest error` record in your project.

| What | Why | What to do |
| --- | --- | --- |
| `Summary` metrics | A legacy OTLP metric type Logfire does not store | Emit a histogram instead |
| `aggregation_temporality` outside 0, 1, or 2 | Not a value OTLP defines | Fix the exporter emitting it |
| A histogram count, bucket count, or zero count above 2,147,483,647 | Logfire stores these counts as 32-bit integers | Reset the counter more often, or use delta temporality |

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| The exporter logs `413` and a batch never arrives | The request was over 100 MB | Lower the export batch size, or stop attaching very large values to every record |
| Nothing from one host arrives, and `logfire ingest error` records mention timestamps | That host's clock has drifted past the window | Run a time sync daemon on the host |
| A backfill or replay produces no data | The records are older than 24 hours | Backfilling historical data is not supported |
| An attribute shows `...` in the middle | The record was over the 10 MB attribute budget | Check the **Truncation** panel on the record to see everything that was cut |
| A message is cut short and the rest is nowhere | The message field stores 512 bytes | Also write the full text to an attribute of your own |
| A metric appears in the SDK but never in Logfire | It is a `Summary` metric, or a count overflowed 32 bits | Emit a histogram; check for a `logfire ingest error` record naming the metric |

## Next steps

- [Alternative clients](../how-to-guides/alternative-clients.md): send data with any OpenTelemetry SDK, and set the export endpoint and protocol correctly.
- [Scrubbing](../how-to-guides/scrubbing.md): stop sensitive values leaving your machine, which also keeps large payload fields out of your telemetry.
- [Sampling](../how-to-guides/sampling.md): keep a representative subset of traces to control volume and cost.
