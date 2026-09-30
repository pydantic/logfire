---
title: "Send data through a Collector"
description: "Run an OpenTelemetry Collector in front of Logfire in a few minutes, with the smallest configuration that works."
---
# Send data through a Collector

Get an OpenTelemetry Collector running in front of Logfire, with your application sending through it instead of straight to Logfire. This is the base that every other guide in this section builds on.

If you have not decided whether you need a Collector at all, read [when you need one](otel-collector-overview.md#when-you-need-one) first.

## Before you start

You need a [write token](../create-write-tokens.md) for the project you want data to land in, and Docker or a downloaded Collector binary.

## Write the configuration

This is the smallest configuration that does something useful: accept data from your applications and forward it to Logfire.

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  otlphttp:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp]
```

The endpoint must be the region your project lives in. The `batch` processor groups data into fewer, larger requests and belongs in every pipeline you run.

## Run it

```bash
docker run --rm \
  -p 4318:4318 \
  -e LOGFIRE_TOKEN='<your-write-token>' \
  -v "$(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:latest
```

The `contrib` build includes every component the other guides in this section use. The core build is smaller but does not have them.

To check the file before starting anything, run `validate` in the same image:

```bash
docker run --rm \
  -v "$(pwd)/otel-collector-config.yaml:/tmp/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:latest \
  validate --config=file:/tmp/config.yaml
```

## Point your application at it

Set the endpoint and turn off sending straight to Logfire, so the Collector is the only path out:

```python skip-run="true" skip-reason="external-connection"
import os

os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://localhost:4318'

import logfire

logfire.configure(send_to_logfire=False)

with logfire.span('hello from the collector'):
    logfire.info('it works')
```

The SDK appends `/v1/traces`, `/v1/metrics`, and `/v1/logs` to that endpoint on its own.

Non-Python applications need no Logfire-specific setup, but the receiver above accepts OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive data, over HTTP only. Some OpenTelemetry SDKs default to sending it over gRPC, a different transport, on port 4317 instead. Set the protocol as well as the endpoint:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

To accept gRPC instead, add a `grpc` protocol block to the receiver alongside `http`.

## Verify data arrives

Open your project's Live view. The `hello from the collector` span should arrive within a few seconds.

If nothing appears, add a `debug` exporter so the Collector prints what it is handling:

```yaml title="otel-collector-config.yaml"
exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp, debug]
```

Spans in the Collector's output but not in Logfire means the problem is the exporter: check the region and the token. No spans in the output means the problem is upstream: check that your application is pointed at the right port.

## Troubleshoot the Collector

**The Collector starts and exits immediately.** A configuration error. Run `validate` as shown above; the error names the block it could not read.

**`401 Unauthorized` in the Collector's logs.** The write token is wrong, or the endpoint does not match the region the project lives in. Check both.

**The Collector runs and logs nothing at all.** A component that is defined but not listed under `service.pipelines` does nothing. Check that your receiver and exporter both appear in a pipeline.

**Connection refused from the application.** The receiver binds to `0.0.0.0:4318` inside the container, so the port has to be published with `-p 4318:4318`. From another container, use the Collector's service name rather than `localhost`.

## Next steps

- [Collect host metrics](host-monitoring.md) from the machine the Collector runs on, with no application changes.
- [Control volume and cost](control-volume-and-cost.md) by dropping traffic you never look at.
- [Scrub sensitive data](otel-collector-scrubbing.md) centrally, so every application inherits the same rules.
