# Airflow

Airflow has a native OpenTelemetry integration for [traces] and [metrics].

Airflow creates an exporter internally, which sends data to the configured backend.

Unfortunately, it's not possible to send data to Logfire directly, yet... But we are working on it. :wink:

??? question "Why it's not possible to send data directly?"
    The Airflow implementation doesn't allow to override the headers used by the exporter.
    See [apache/airflow#44346](https://github.com/apache/airflow/pull/44346) for more details.

    We need the ability to set the authorization header to send data to **Logfire**.
    See our [Alternative clients section](../guides/advanced/alternative-clients.md).

## Setup

To enable the OpenTelemetry integration in Airflow, you'll need to have an [OpenTelemetry Collector] running, and then
configure Airflow to send data to it.

### OpenTelemetry Collector

The OpenTelemetry Collector is a vendor-agnostic agent that can collect traces and metrics from your applications and
send them to various backends.

In this case, we are interested in sending data to **Logfire**. :fire:

!!! note
    Using a collector is an option when you are already sending data to a backend, but you want to migrate to **Logfire**.

    Then you can configure the collector to send data to **Logfire**, as well as your current backend. This way you can
    compare the data and ensure that everything is working as expected. Cool, right? :sunglasses:

You can check the [OpenTelemetry Collector installation] guide to set it up, but I'll help you with the configuration.

```yaml title="otel-collector-config.yaml"
receivers:  # (1)!
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

exporters:  # (2)!
  debug:  # (3)!
  otlphttp:
    endpoint: https://logfire-api.pydantic.dev/
    compression: gzip
    tls:
      insecure: true
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"  # (4)!

processors:
  batch:
    timeout: 1s
    send_batch_size: 32768

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"

service:  # (5)!
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp]
```

1. Define the receivers to collect data from your applications.

    See more about it on the [OpenTelemetry Collector Receiver] section.

2. Define the exporters to send data to **Logfire**.

    The `otlphttp` exporter is used to send data to **Logfire**.

3. The `debug` exporter is used to send data to the console, so you can see what's being sent.

    This is useful for debugging purposes, but it can be removed in production.

4. Set the `Authorization` header to send data to **Logfire**.

    The `{env:LOGFIRE_TOKEN}` will be replaced by the environment variable.

5. Define the service to configure the pipelines.

    The `traces` pipeline is used to send trace data, and the `metrics` pipeline is used to send metrics data.

## Airflow configuration

To configure Airflow to send data to the OpenTelemetry Collector, we'll need the following settings:

- [Metrics Configuration][metrics]
- [Traces Configuration][traces]

On your `airflow.cfg` file, add the following configuration:

```ini title="airflow.cfg"
[metrics]
otel_on = True
otel_host = localhost
otel_port = 4318
otel_prefix = airflow
otel_interval_milliseconds = 30000  # The interval between exports, defaults to 60000
otel_ssl_active = False

[traces]
otel_on = True
otel_host = localhost
otel_port = 4318
otel_prefix = airflow
otel_ssl_active = False
otel_task_log_event = True
```

[traces]: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/traces.html
[metrics]: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/metrics.html
[OpenTelemetry Collector]: https://opentelemetry.io/docs/collector/
[OpenTelemetry Collector installation]: https://opentelemetry.io/docs/collector/installation/
[OpenTelemetry Collector Receiver]: https://opentelemetry.io/docs/collector/configuration/#receivers
