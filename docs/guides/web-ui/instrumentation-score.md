---
title: "Find gaps in your instrumentation"
description: "Use the Instrumentation Score to find missing metadata, noisy traces, and other telemetry issues you can fix in Logfire."
---
# Instrumentation score

Find the services whose telemetry is hard to filter, compare, or use for debugging. Logfire checks the traces, metrics, and logs it receives against the [OpenTelemetry Instrumentation Score specification](https://github.com/instrumentation-score/spec) and shows you which fixes to prioritize.

!!! info "Experimental"
    Instrumentation score is experimental. [Contact Pydantic](https://pydantic.dev/contact) to request access.

## Open the score

1. Open your Logfire project and select **Instrumentation score** in the project sidebar.
2. To check one service, open [Services](services.md), select the service, and choose **Instrumentation score** on its detail page.
3. Select **Refresh** after new telemetry arrives to update the score.

## Investigate a failing check

The score ranges from 0 to 100. Rules with greater impact contribute more to the score. Logfire shows which rules fail and which services have failing data.

Open a failing rule to see why it matters and how to fix it. Choose **View trace** when a trace is available, or **Open query in Explore** to inspect the query and its results in [Explore](explore.md).

For example, **Metrics have a valid unit** can fail when a service reports request counts with an empty unit. Set the instrument's unit to `{request}`, let the service send new metrics, and refresh. Earlier points can still count until they leave the check window.

## Read the score in context

Regular checks use the last hour. Pattern checks run over the last 15 minutes. Some checks use a sample, such as the checks for missing parent spans and sensitive data in spans. Open a rule to see how Logfire checks it and what limits apply.

The sensitive-span check runs on a service's score. The production debug check uses the OpenTelemetry environment name `production`. Set `deployment.environment.name` to `production` on telemetry from production services.

If a check has no data, send the relevant telemetry and refresh. If a check reaches its service limit, filter the project by environment or open the score for one service.

For related setup, see how to [send service attributes](services.md#send-the-attributes-the-page-needs).
