# Advanced scrubbing with the OTel Collector

The Logfire SDK already comes with powerful, [built-in scrubbing](../scrubbing.md) to automatically protect sensitive data within your application.
For most use cases, adding `extra_patterns` or using a `callback` is all you need.

However, as your system grows, you may need more powerful, centralized, and conditional scrubbing logic. This is where the [OpenTelemetry (OTel) Collector](./otel-collector-overview.md) shines.
By using the collector as a central hub, you can apply complex data transformation rules before data reaches our backend, without adding overhead to your applications.

This guide will walk you through advanced scrubbing techniques using OTel Collector processors.

Please take a look at the [OTel Collector overview](./otel-collector-overview.md) first if you aren't already using it.

### Why Use the Collector for Scrubbing?

* **Centralized Governance:** Manage scrubbing rules for all your services in one place.
* **Performance**: Offload the processing work from your application to the collector, keeping your services lean and fast.
* **Advanced Logic:** Implement rules that are too complex for the SDK, such as scrubbing data conditionally based on other attributes (e.g., only scrub PII from failed requests).
* **Language Agnostic:** The same scrubbing rules apply whether your services are written in Python, Java, Go, or any other language.

---

### Scenario 1: Replicating SDK Behavior (The attributes Processor)

The SDK is great at scrubbing data based on a list of patterns that match attribute keys (like password or session). You can replicate and extend this in the collector.

This is useful if you want to enforce a baseline set of scrubbed keys for all services sending data to the collector.

**Use Case:** You want to ensure any attribute with the key session-id, user-token, or password somewhere in the key is completely removed from all telemetry.

**Solution:** Use the [attributes processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/attributesprocessor/README.md) with the delete action.

Collector `config.yaml` snippet:
```yaml
processors:
  # The attributes processor is great for acting on specific, known keys.
  attributes/remove_sensitive_keys:
    actions:
      # Use 'delete' to completely remove the key-value pair.
      - key: session_id
        action: delete
      - key: user_token
        action: delete
      # You can add your own custom patterns here, just like the SDK's 'extra_patterns'. This pattern will remove any attribute key that contains the word "password".
      - pattern: "password"
        action: delete
```

---

### Scenario 2:  Scrubbing Sensitive Values with Regex (The redaction Processor)

Sometimes, sensitive data isn't in a predictable key; it's in the value itself. For example, a user might include their email address in a log message or a trace attribute.
The SDK scrubbing already supports this too, but you might want to mask or hash only the sensitive string instead of the full value.

**Use Case:** You want to find and mask any email address, no matter where it appears in your telemetry data.

**Solution:** Use the [redaction processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/redactionprocessor/README.md). It can search all attribute values and log bodies for regex patterns and replace them.

Collector `config.yaml` snippet:
```yaml
processors:
  # The redaction processor is perfect for finding and masking patterns within values.
  redaction/mask_pii:
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

### Scenario 3: Conditional Scrubbing with Logic (The transform Processor)

The real power of the collector is unlocked when you move beyond simple scrubbing and apply conditional logic. What if you only want to remove sensitive data when a transaction fails? This allows you to keep valuable data for successful requests while protecting user information in error traces.

**Use Case:** You want to scrub the `credit_card_number` attribute, but **only** if the transaction failed (e.g., `http.status_code` is 500 or greater).

**Solution:** Use the [transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/transformprocessor/README.md) and its powerful query language, OTTL.

Collector `config.yaml` snippet:
```yaml
processors:
  # The transform processor allows for complex, conditional logic using OTTL.
  transform/conditional_scrubbing:
    # We define rules for our trace signals (spans).
    trace_statements:
    # In plain English: "Set the span's 'credit_card_number' attribute to '[REDACTED]' but only where the span's 'http.status_code' attribute is 500 or more."
      - set(span.attributes["credit_card_number"], "[REDACTED]") where span.attributes["http.status_code"] >= 500
```

---

## Putting It All Together: A Full Example

To use these processors, you need to add them to a service pipeline in your collector configuration. The data will flow through them in the order you specify.

Here is a complete `config.yaml` showing how to chain these processors together:

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
  # First, do simple key-based scrubbing.
  attributes/remove_sensitive_keys:
    actions:
      - key: session_id
        action: delete

  # Next, find and mask any PII values we missed.
  redaction/mask_pii:
    allow_all_keys: true
    blocked_values:
     - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

  # Finally, apply complex conditional rules.
  transform/conditional_scrubbing:
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
      processors: [attributes/remove_sensitive_keys, redaction/mask_pii, transform/conditional_scrubbing]
      exporters: [otlphttp, debug]
    logs:
      receivers: [otlp]
      processors: [attributes/remove_sensitive_keys, redaction/mask_pii]
      exporters: [otlphttp, debug]
```

With this, you have an idea of what you can accomplish setting up data scrubbing in your OTel Collector config.

For a full list of OTel Collector available processors, with examples and their full specs, take a look at the [opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor) repository.
