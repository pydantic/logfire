# Advanced scrubbing with the OTel Collector

The Logfire SDK already comes with powerful, [built-in scrubbing](../scrubbing.md) to automatically protect sensitive data within your application.
For most use cases, adding `extra_patterns` or using a `callback` is all you need.

However, as your system grows, you may need more powerful, centralized, and conditional scrubbing logic. This is where the [OpenTelemetry (OTel) Collector](./otel-collector-overview.md) really stands out.
By using the collector as a central hub, you can apply complex data transformation rules before data reaches our backend, without adding overhead to your applications.

This guide will walk you through advanced scrubbing techniques using OTel Collector processors.

Please take a look at the [OTel Collector overview](./otel-collector-overview.md) first if you aren't already using it.

### Why Use the Collector for Scrubbing?

* **Performance**: Offload the processing work from your application to the collector, keeping your services lean and fast.
* **Advanced Logic:** Implement rules that are too complex for the SDK, such as scrubbing data conditionally based on other attributes (e.g., only scrub PII from failed requests).
* **Language Agnostic:** The same scrubbing rules apply whether your services are written in Python, Java, Go, or any other language.

---

:page_facing_up: **Note:** Make sure you set `logfire.configure(send_to_logfire=False)` where you want to apply data transformation, otherwise traces that reach logfire will not have the desired modifications. You can take a look at [Alternative Backends](../alternative-backends.md).

---

### Scenario 1: Scrubbing or Removing Attributes by Key

The [attributes processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/attributesprocessor/README.md) works well for acting on known attribute keys.

For example, here's a config snippet showing how to:
- Replace any attribute with the _exact_ keys `session_id` or `user_token` with 'SCRUBBED'
- Remove completely any key that _contains_ `password`
```yaml
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

---

### Scenario 2:  Masking Sensitive Values with Regex

The [redaction processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/redactionprocessor/README.md) can mask or hash regex patterns _within_ a value instead of scrubbing the whole thing. For example, here's how to mask email addresses:

Collector `config.yaml` snippet:
```yaml
processors:
  # The redaction processor is perfect for finding and masking patterns within values.
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

 ---

### Scenario 3: Conditional Scrubbing with Logic

The [transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/transformprocessor/README.md) has a powerful query language called OTTL which lets you apply conditional logic. For example, here's how to scrub the `credit_card_number` attribute, but **only** if the transaction failed, i.e. `http.status_code` is 500 or greater.

```yaml
processors:
  transform:
    trace_statements:
      - set(span.attributes["credit_card_number"], "[REDACTED]") where span.attributes["http.status_code"] >= 500
```

---

## Complete Example

To use these processors, you need to add them to a service pipeline in your collector configuration. The data will flow through them in the order you specify.

Here is a complete `config.yaml` showing how you might chain these processors together:

```yaml
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
    - key: session_id
      action: update
      value: "[Scrubbed due to session_id]"
    - key: user_token
      action: update
      value: "[Scrubbed due to user_token]"

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

Now you should have a clearer sense of what's possible using the OpenTelemetry Collector processors for data scrubbing.

 Remember, for this scrubbing to work, ensure all telemetry data is only routed through the OTel Collector by setting `logfire.configure(send_to_logfire=False)`
