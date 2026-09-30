---
title: "Migrate from AWS (CloudWatch / X-Ray) to Logfire"
description: "Swap the AWS Distro for OpenTelemetry (ADOT) Collector's awsemf/awsxray exporters for an otlphttp exporter pointed at Logfire."
---

# Migrate from AWS (CloudWatch / X-Ray)

If you send telemetry to Amazon CloudWatch and AWS X-Ray, you're most likely running the **AWS Distro for OpenTelemetry** (ADOT) Collector, exporting through the `awsxray` (traces), `awsemf` (metrics), and `awscloudwatchlogs` (logs) exporters. ADOT is a standard OpenTelemetry Collector, so migrating to Logfire means swapping those AWS exporters for an `otlphttp` exporter — see [Migrate to Logfire](overview.md) for the general shape.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If you run the ADOT Collector

Replace the AWS exporters with one that targets Logfire, and reference it from each pipeline. Your receivers and processors don't change.

The AWS exporters carry no credentials — they authenticate through the instance/task IAM role (the AWS SDK credential chain). Logfire uses a write token instead, in the `Authorization` header below.

```yaml
exporters:
  # remove (or keep alongside during cutover):
  # awsxray: {}
  # awsemf: {}
  # awscloudwatchlogs:
  #   log_group_name: "your-log-group"
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      exporters: [otlphttp/logfire]
    metrics:
      exporters: [otlphttp/logfire]
    logs:
      exporters: [otlphttp/logfire]
```

Because a pipeline can fan out, you can keep the AWS exporters and add `otlphttp/logfire` alongside them to run in parallel, then remove the AWS ones once you've rebuilt what you need in Logfire.

## If your apps export OTLP

If your services export OpenTelemetry Protocol (OTLP) straight to the ADOT Collector's OTLP receiver, point the SDK at Logfire instead:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Host & Kubernetes monitoring](../how-to-guides/otel-collector/otel-collector-overview.md) — collect infrastructure metrics with the Collector, the CloudWatch-style signals you may be replacing
- AWS's own docs, to confirm your current ADOT exporters: [AWS Distro for OpenTelemetry — Collector](https://aws-otel.github.io/docs/getting-started/collector)
