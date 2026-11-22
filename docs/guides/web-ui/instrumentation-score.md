---
title: "Find gaps in your instrumentation"
description: "Find and fix telemetry problems in Logfire, from missing service names and broken traces to inconsistent metric units."
---
# Instrumentation Score

Find which services send telemetry that makes debugging harder. When a trace has gaps or a latency chart mixes seconds and milliseconds, use the Instrumentation Score to see which service to fix and what to change.

Logfire checks your traces, metrics, and logs using rules from the [Instrumentation Score specification for OpenTelemetry](https://github.com/instrumentation-score/spec). A trace follows a request through your system, and each span records one operation in that trace.

!!! info "Experimental"

    Instrumentation Score is experimental. [Contact Pydantic](https://pydantic.dev/contact) to request access.

## Recognize common problems

| What you notice | What the score helps you find | What to change |
|-----------------|-------------------------------|----------------|
| Several services appear under `unknown_service`. | Missing service names make it hard to find who sent the data. | [Set a stable service name](services.md#send-the-attributes-the-page-needs) such as `checkout-api`. |
| A trace has gaps or is hard to read. | An operation can appear without its parent operation, or repeated work can produce many very short spans. | Pass trace context, the IDs that connect operations across services, and check that parent spans reach Logfire. Record repeated work with one span and a count when that gives you enough detail. |
| Latency looks inconsistent across services. | Services report the same metric in different units or count measurements in different ranges, called histogram buckets. | Use the same unit and bucket boundaries across services. Convert the measurements when you change their unit. |
| A request counter creates a separate series for every request. | An attribute such as a request ID has thousands of distinct values. Each combination of attribute values can create a separate metric series. | Remove the request ID from the metric. Use a route template such as `/orders/{id}` to group requests by endpoint. |
| Debug logs are making production logs harder to scan. | The check flags debug logs from the OpenTelemetry environment named `production`. | Set `deployment.environment.name` to `production` for production services, then raise the minimum log level. See [how to configure environments](../../how-to-guides/environments.md). |
| An email address or credential appears in telemetry. | The sensitive-data checks look for common patterns in spans, metrics, logs, and resource attributes, which describe the service or host sending the data. | Remove the field or [scrub sensitive values](../../how-to-guides/scrubbing.md) before they reach Logfire. |

## Investigate a finding

1. Open your project and choose **Instrumentation score** in the sidebar. For a single service, open its detail page in [Services](services.md) and choose **Instrumentation score** there.
2. Start with **Fix first**. Open a failing rule to see which services it affects and read **How to fix**.
3. Choose **View trace** when a trace is available, or **Open query in Explore** to inspect the check in [Explore](explore.md).
4. After you deploy a fix and new telemetry arrives, select **Refresh**. The page shows a new score and check results when the queries finish. Older records can still cause a check to fail until they leave its window.

For example, **Each metric name has one unit** can flag a latency metric that checkout sends in milliseconds and payments sends in seconds. Record the metric in seconds in both services. In checkout, convert the values to seconds before recording them and set the unit to `s`. After the older points leave the check window, refresh and review the rule again.

## Read the score in context

The score ranges from 0 to 100. Higher-impact rules carry more weight, and the score includes checks that ran and had data. When you compare scores, use the same environment filters and check which rules contributed.

Regular checks use the last hour. Pattern checks use the last 15 minutes. Some rules sample traces or use pattern matching to find common problems. Open a rule for its coverage details. The sensitive-span check runs on a single service's score.

If a rule shows **No data to check**, confirm the expected telemetry is arriving and refresh. If a check reaches its service limit, filter by environment or open the score for one service.
