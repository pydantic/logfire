---
title: "Ingest limits"
description: "The limits Logfire applies to the data you send, what happens when data exceeds them, and how to tell."
---

# Ingest limits

Logfire applies a few limits to the data you send. Going past one either **drops** the data or **shortens** a value, and this page covers which, and what to do about it.

| Limit | Value | What happens past it |
| --- | --- | --- |
| Request size | 100 MB | The request is rejected and none of it is stored |
| Timestamp range | 24 hours in the past to 1 hour in the future | Records outside the window are dropped; the rest of the request is stored |
| Attributes per record | 10 MB | Oversized values are shortened; the record is stored |
| Long text fields | 512 bytes for span names, messages, and service names; 32,000 bytes for exception messages and stack traces | The value is shortened; the record is stored |

The limits are the same in the [US and EU regions](data-regions.md) and are not configurable per project. Separately, [Summary metrics](#summary-metrics-are-not-supported) are not stored at all.

## Timestamps

Logfire accepts timestamps from **24 hours in the past** to **1 hour in the future**, measured against Logfire's clock when the request arrives, not the clock of the machine that sent it. Every timestamp is checked: a span's start and end, each span event, a log's timestamp, and each metric data point.

This is the limit that most often looks like data silently going missing, because the request itself succeeds. Records outside the window are dropped, the rest of the request is stored, and Logfire writes an explanation into your project as a span named `logfire ingest error`. Search for that if data you expected never arrived.

The usual causes are a wrong clock on the sending host, data buffered offline and exported much later, and attempts to load historical data. Backfilling records older than 24 hours is not supported.

## Truncation

Attributes and long text fields are never rejected for being too big, only shortened. A record whose attributes exceed 10 MB has its largest values cut down until it fits, and a log's `body` gets its own 10 MB budget separate from the much shorter message.

Values cut to fit that budget are listed in the record's `logfire.truncated` attribute, and the record's detail panel in the [Live view](../guides/web-ui/live.md) shows a **Truncation** section naming them. The fixed-length fields in the table above are a different case: they are shortened silently, so a span name or message cut at 512 bytes is not flagged anywhere.

## Summary metrics are not supported

Logfire does not store OpenTelemetry Protocol (OTLP) `Summary` metrics, a legacy type that reports quantiles the sender has already computed. Quantiles that arrive pre-computed cannot be re-aggregated: averaging two p95 values from two hosts does not give the p95 across both.

A `Summary` is dropped and never reaches the metrics catalog, while the other metrics in the same request are stored. They usually come from a Prometheus scrape forwarded through an OpenTelemetry Collector, whose `prometheus` receiver turns every Prometheus summary into an OTLP `Summary`. Send a histogram instead and compute percentiles at query time.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| The exporter reports the payload is too large and a batch never arrives | The request was over 100 MB | Lower the batch size for that signal (`OTEL_BSP_MAX_EXPORT_BATCH_SIZE` for spans, `OTEL_BLRP_MAX_EXPORT_BATCH_SIZE` for logs), and shrink individual records: a smaller batch does not help when one record is itself oversized |
| Data from one host never appears, and the project has `logfire ingest error` records | That host's clock has drifted outside the window | Run a time sync daemon on the host |
| A backfill or replay produces no data | The records are older than 24 hours | Backfilling historical data is not supported |
| A value displays with `...` in the middle | The record was over the 10 MB attribute budget | Check the **Truncation** section on the record to see everything that was cut |
| A message is cut short and the rest is nowhere | The message field stores 512 bytes and the original is not kept | Also write the full text to an attribute of your own |
| One metric never appears while others from the same source do | It is an OTLP `Summary` | Send a histogram instead |

## Next steps

- [Alternative clients](../how-to-guides/alternative-clients.md): send data with any OpenTelemetry SDK.
- [Scrubbing](../how-to-guides/scrubbing.md): stop sensitive values leaving your machine, which also keeps large payload fields out of your telemetry.
- [Sampling](../how-to-guides/sampling.md): keep a representative subset of traces to control volume and cost.
