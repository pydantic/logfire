---
integration: built-in
---

# Airflow

**Airflow** has a native OpenTelemetry integration for [traces] and [metrics], which involves creating
an exporter internally that sends data to the configured backend.

To configure **Airflow** to send data to **Logfire**, you'll need to:

- Set the `OTEL_EXPORTER_OTLP_HEADERS` environment variable.
- Configure the `otel_*` settings in the `airflow.cfg` file.

!!! warning
    If your `apache-airflow` is older than 2.10.4, this section will not work for you.

    In that case, go to the [Airflow with OpenTelemetry Collector] section.

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=${LOGFIRE_TOKEN}"
```

Where `${LOGFIRE_TOKEN}` is your [**Logfire** write token][write-token].


```ini title="airflow.cfg"
[metrics]
otel_on = True
otel_host = logfire-api.pydantic.dev
otel_port = 443
otel_prefix = airflow
otel_interval_milliseconds = 30000  # The interval between exports, defaults to 60000
otel_ssl_active = True

[traces]
otel_on = True
otel_host = logfire-api.pydantic.dev
otel_port = 443
otel_prefix = airflow
otel_ssl_active = True
otel_task_log_event = True
```

For more details, check airflow [traces] and [metrics] documentation.

## Airflow with OpenTelemetry Collector

If your `apache-airflow` is older than 2.10.4, it means that you'll not be able to set the `OTEL_EXPORTER_OTLP_HEADERS`
environment variable. :sob:

??? question "Why can't I set the `OTEL_EXPORTER_OTLP_HEADERS` environment variable? :thinking:"
    This was a bug that was fixed in the 2.10.4 version of `apache-airflow`.

    The **Logfire** team fixed it in [apache/airflow#44346](https://github.com/apache/airflow/pull/44346).

In that case, you'll need to set up an [OpenTelemetry Collector] to send data to **Logfire**.

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

### Airflow configuration

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
[metrics]: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/metrics.html#setup-opentelemetry
[OpenTelemetry Collector]: https://opentelemetry.io/docs/collector/
[OpenTelemetry Collector installation]: https://opentelemetry.io/docs/collector/installation/
[OpenTelemetry Collector Receiver]: https://opentelemetry.io/docs/collector/configuration/#receivers
[write-token]: ../../how-to-guides/create-write-tokens.md
