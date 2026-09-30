---
title: "Scrub sensitive data in the Collector"
description: "Data scrubbing with the Logfire OTel Collector: Remove attributes by key, mask sensitive values, or implement conditional scrubbing to guard sensitive data."
---
# Scrub sensitive data in the Collector

The Logfire SDK [scrubs sensitive data](../scrubbing.md) from the spans and logs it sends, before they leave your machine. For most cases, adding `extra_patterns` or a `callback` is all you need. Two things fall outside it: metric attributes, which the SDK does not scrub, and telemetry that reaches Logfire by another route, such as a service exporting OTLP directly.

As your system grows, you may want one set of rules that applies to every service, or rules that depend on the data itself. The [OpenTelemetry Collector](./otel-collector-overview.md) applies them centrally, before the data reaches Logfire, without adding work to your applications.

If you are not running a Collector yet, start with [Send data through a Collector](send-data-through-a-collector.md).

## Why scrub in the Collector

* **Cost to your app**: the Collector does the work, not your services.
* **Conditional rules**: redact based on other attributes, such as only on failed requests. The SDK cannot express this.
* **Every language at once**: the same rules apply to Python, Java, Go, and anything else sending to the Collector.

!!! note
    Set `logfire.configure(send_to_logfire=False)` in any application whose data the Collector modifies. Otherwise that application also sends an unmodified copy straight to Logfire, and your redaction rules are bypassed.

## Remove or replace an attribute by key

The [attributes processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/attributesprocessor/README.md) works well for acting on known attribute keys.

For example, here's a config snippet showing how to:
- Replace any attribute with the _exact_ keys `session_id` or `user_token` with 'SCRUBBED'
- Remove completely any key that _contains_ `password`
```yaml title="otel-collector-config.yaml"
processors:
  attributes:
    actions:
      - key: session_id
        action: update
        value: "SCRUBBED"
      - key: user_token
        action: update
        value: "SCRUBBED"
      # Using `pattern` instead of `key` matches any key containing the pattern
      - pattern: "password"
      # Remove the key completely instead of replacing
        action: delete
```

## Mask a value inside a longer string

The [redaction processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/redactionprocessor/README.md) can mask or hash regex patterns _within_ a value instead of scrubbing the whole thing. For example, here's how to mask email addresses:

Collector `config.yaml` snippet:
```yaml title="otel-collector-config.yaml"
processors:
  # The redaction processor finds and masks patterns inside values.
  redaction:
    # Flag to allow all span attribute keys. In this case, we want this set to true because we only want to block values.
    allow_all_keys: true
    # BlockedValues is a list of regular expressions for blocking span attribute values. Values that match are masked.
    blocked_values:
     - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    # You can also enable a hash function. By default, no hash function is used and masking with a fixed string is performed.
    # hash_function: md5
```

* **Before:** `user.comment` = "My email is `test@example.com`, please contact me."

* **After:** `user.comment` = "My email is `***`, please contact me."

## Scrub only when a condition holds

The [transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/transformprocessor/README.md) uses a query language called OTTL for conditional logic. For example, here is how to scrub the `credit_card_number` attribute, but **only** if the transaction failed, i.e. `http.status_code` is 500 or greater.

```yaml title="otel-collector-config.yaml"
processors:
  transform:
    trace_statements:
      - set(span.attributes["credit_card_number"], "[REDACTED]") where span.attributes["http.status_code"] >= 500
```

## A complete configuration

To use these processors, you need to add them to a service pipeline in your Collector configuration. The data will flow through them in the order you specify.

Here is a complete `config.yaml` showing how you might chain these processors together:

```yaml title="otel-collector-config.yaml"
# 1. RECEIVERS: How the collector ingests data
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

# 2. PROCESSORS: How we scrub and modify the data
processors:
  # First, do simple key-based scrubbing/removal.
  attributes:
    actions:
      - key: session_id
        action: update
        value: "[Scrubbed due to session_id]"
      - key: user_token
        action: update
        value: "[Scrubbed due to user_token]"
      # Remove any key containing `password` outright.
      - pattern: "password"
        action: delete

  # Next, find and mask any PII values we missed.
  redaction:
    allow_all_keys: true
    blocked_values:
     - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

  # Finally, apply complex conditional rules.
  transform:
    trace_statements:
      - set(span.attributes["credit_card_number"], "[REDACTED]") where span.attributes["http.status_code"] >= 500

# 3. EXPORTERS: Where the scrubbed data is sent
exporters:
  debug:
  otlphttp:
    # Configure the US / EU endpoint for Logfire.
    # - US: https://logfire-us.pydantic.dev
    # - EU: https://logfire-eu.pydantic.dev
    endpoint: "https://logfire-eu.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

# 4. SERVICE: The pipeline that connects everything
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes, redaction, transform]
      exporters: [otlphttp, debug]
    logs:
      receivers: [otlp]
      processors: [attributes, redaction]
      exporters: [otlphttp, debug]
```

## Next steps

- [Control volume and cost](control-volume-and-cost.md) in the same pipeline.
- [Scrubbing in the SDK](../scrubbing.md) for the rules that ship by default.
