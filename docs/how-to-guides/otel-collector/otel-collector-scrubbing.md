---
title: "Scrub sensitive data in the Collector"
description: "Data scrubbing with the Logfire OTel Collector: Remove attributes by key, mask sensitive values, or implement conditional scrubbing to guard sensitive data."
---
# Scrub sensitive data in the Collector

The Logfire SDK [scrubs sensitive data](../scrubbing.md) from the spans and logs it sends, before they leave your machine. For most cases, adding `extra_patterns` or a `callback` is all you need.

Several things sit outside it, and they are the reason this page exists:

- **Model inputs and outputs.** The SDK deliberately does not scrub `gen_ai.input.messages`, `gen_ai.output.messages`, or `pydantic_ai.all_messages`, because a model saying "your password has been reset" would trip every pattern you wrote. See [LLM and AI messages](../scrubbing.md#llm-and-ai-messages).
- **Values the SDK treats as structural**, such as `http.url`, `url.query`, and `db.statement`. A query string or a statement with a literal in it carries whatever you put there.
- **Metric attributes**, which the SDK does not scrub at all.
- **Telemetry that reaches Logfire by another route**, such as a service exporting OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive data, straight to the API.

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
- Remove completely any key that _contains_ `password`, whatever its case
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
      # `pattern` matches the key by regular expression instead of exactly.
      # It is case sensitive, so `(?i)` is what makes it catch `dbPassword` and `PASSWORD`.
      - pattern: "(?i)password"
      # Remove the key completely instead of replacing its value
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

!!! warning
    Keep `allow_all_keys: true` unless you mean to use an allowlist. This processor fails closed:
    with no `allowed_keys` and the flag removed, it strips **every** attribute from every span
    rather than only masking the values you blocked. That is deliberate upstream behaviour, and it
    is easy to trigger by deleting what looks like a redundant line.

## Scrub only when a condition holds

The [transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/transformprocessor/README.md) uses the OpenTelemetry Transformation Language (OTTL), a small expression language for rewriting telemetry, so a rule can depend on the rest of the span.

A request body is the usual case. You want it when something went wrong and you are debugging, and you do not want it sitting in storage for the millions of requests that succeeded:

```yaml title="otel-collector-config.yaml"
processors:
  transform:
    trace_statements:
      - set(span.attributes["http.request.body.text"], "[REDACTED]")
          where span.attributes["http.request.body.text"] != nil
            and (span.attributes["http.response.status_code"] == nil or span.attributes["http.response.status_code"] < 500)
            and (span.attributes["http.status_code"] == nil or span.attributes["http.status_code"] < 500)
```

Read the condition carefully before copying it, because each clause is load-bearing:

- **It redacts on everything except server errors**, which is the direction you usually want: keep the evidence where you need it, drop it everywhere else. Written the other way round, redacting only on failure, it leaves the body in place for every successful request, which is almost never what anyone means.
- **The `!= nil` guard matters.** `set` creates an attribute that was not there, so without it every span under 500 gains a `[REDACTED]` body it never had.
- **Both status attributes are checked.** `http.status_code` is the older spelling and `http.response.status_code` the current one; instrumentations differ, and the SDK itself reads both. Checking only one gets it wrong in the dangerous direction: the unchecked attribute is absent as far as the rule is concerned, so a span that really was a server error looks like a success and has its body removed. Checking both means a 500 under either spelling keeps its body.
- **A missing status still redacts.** Each status clause passes when the attribute is absent, so a span with no status code is treated as "not a server error" and its body is removed, rather than being kept by accident.

`http.request.body.text` is what the Logfire HTTP integrations emit when you turn body capture on; `http.request.body.form` is the other one. Substitute whatever key your own instrumentation uses.

`trace_statements` applies to spans only. Logs and metrics need their own statements, which is why the complete configuration below does not put `transform` in those pipelines.

## A complete configuration

To use these processors, you need to add them to a service pipeline in your Collector configuration. The data will flow through them in the order you specify.

Here is a complete configuration showing how to chain these processors together. It reads your write token from `LOGFIRE_TOKEN`, so export that where the Collector runs:

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
      # Remove any key containing `password`, in any case, outright.
      - pattern: "(?i)password"
        action: delete

  # Next, find and mask any PII values we missed.
  redaction:
    allow_all_keys: true
    blocked_values:
     - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

  # Finally, apply conditional rules. This keeps the request body only where it helps,
  # on server errors, and redacts it everywhere else.
  transform:
    trace_statements:
      - set(span.attributes["http.request.body.text"], "[REDACTED]")
          where span.attributes["http.request.body.text"] != nil
            and (span.attributes["http.response.status_code"] == nil or span.attributes["http.response.status_code"] < 500)
            and (span.attributes["http.status_code"] == nil or span.attributes["http.status_code"] < 500)

# 3. EXPORTERS: Where the scrubbed data is sent, reading LOGFIRE_TOKEN from the environment
exporters:
  # `detailed` is what makes the Collector print each attribute, which is how the
  # verification step below shows you whether a rule fired.
  debug:
    verbosity: detailed
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
    metrics:
      receivers: [otlp]
      processors: [attributes, redaction]
      exporters: [otlphttp, debug]
```

The `metrics` pipeline matters more than it looks. The note above tells you to set
`send_to_logfire=False`, so the Collector is the only way out; leave the pipeline off and your
applications' metrics are dropped without a word. It also carries `attributes` and `redaction`,
which is what closes the metric-attribute gap named at the top of this page. `transform` is not
in it, because `trace_statements` only applies to spans.

The `debug` exporter prints what the Collector is handling, so you can confirm a rule fires
before trusting it. Drop it once you have.

## Verify a rule fires

Do this before you trust a rule with production data. Send one span carrying a value the rule
should remove, and read the Collector's own output rather than waiting to see what reaches
Logfire:

```bash
curl -s -X POST http://localhost:4318/v1/traces \
  -H 'Content-Type: application/json' \
  -d '{"resourceSpans":[{"scopeSpans":[{"spans":[{
        "traceId":"5b8efff798038103d269b633813fc60c",
        "spanId":"eee19b7ec3c1b174","name":"login","kind":1,
        "startTimeUnixNano":"1544712660000000000","endTimeUnixNano":"1544712661000000000",
        "attributes":[
          {"key":"session_id","value":{"stringValue":"sess-123"}},
          {"key":"user.comment","value":{"stringValue":"mail me at test@example.com"}},
          {"key":"http.request.body.text","value":{"stringValue":"{\"card\":\"4111\"}"}},
          {"key":"http.response.status_code","value":{"intValue":"200"}}]}]}]}]}'
```

The `debug` exporter prints each span it handles. All three rules should have fired on it:

| Attribute | Expected |
| --- | --- |
| `session_id` | `[Scrubbed due to session_id]`, not `sess-123` |
| `user.comment` | the address masked, so `mail me at ****` |
| `http.request.body.text` | `[REDACTED]`, because the status is below 500 |

Change the status to `500` and send it again: the body should survive, because that is the case
the rule keeps evidence for. If any attribute still shows its original value, that rule did not
match.

## Troubleshoot scrubbing

**A rule matches nothing.** `pattern` is a regular expression on the attribute key and it is case
sensitive, so `password` does not match `dbPassword`. Use `(?i)` for any spelling, as the example
above does.

**Values still arrive unredacted in Logfire.** The application is probably also sending straight to
Logfire, so an unmodified copy arrives alongside the one the Collector cleaned. Set
`send_to_logfire=False`, as the note near the top of this page says.

**Metrics stopped arriving.** The configuration has no `metrics` pipeline. With
`send_to_logfire=False` the Collector is the only way out, so a missing pipeline drops that signal
silently.

**A condition never fires.** OTTL compares types strictly: `span.attributes["http.status_code"]`
is an integer when the instrumentation sets it as one, and a comparison against a string will not
match. Add a `debug` exporter and read the attribute as the Collector sees it.

## Next steps

- [Control volume and cost](control-volume-and-cost.md) in the same pipeline.
- [Scrubbing in the SDK](../scrubbing.md) for the rules that ship by default.
