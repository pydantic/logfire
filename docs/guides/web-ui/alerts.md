---
title: "Logfire Alerts: Status Monitoring & Error Notifications"
description: "Learn how to create alerts based on SQL query conditions (e.g., error count threshold). Use Logfire to track status changes and send notifications via Slack, Opsgenie, webhooks, or email."
---
With **Logfire**, use Alerts to notify you when certain conditions are met.

![Logfire alerts screen](../../images/guide/browser-alerts-full.png)

## Create an alert

Let's see in practice how to create an alert.

1. Go to the **Alerts** tab in the left sidebar.
2. Click the **Create alert** button.

Then you'll see the following form:

![Create alert form](../../images/guide/browser-alerts-create.png)

The **Query** field is where you define the conditions that will trigger the alert.
For example, you can set up an alert to notify you when the number of errors in your logs exceeds a certain threshold.

On our example, we're going to set up an alert that will trigger when an exception occurs in the `api` service
and the route is `/members/{user_id}`.

```sql
SELECT trace_id, exception_type, exception_message FROM records  -- (1)!
WHERE
    is_exception and
    service_name = 'api' and
    attributes->>'http.route' = '/members/{user_id}'  -- (2)!
```

1. The `SELECT ... FROM records` statement is the base query that will be executed. The **records** table contains the spans and logs data. `trace_id` links to the trace in the live view when viewing the alert run results in the web UI.
2. The `attributes` field is a JSON field that contains additional information about the record. In this case, we're using the `http.route` attribute to filter the records by route.

The **Time window** field allows you to specify the time range over which the query will be executed.

The **Channel** field is where you select how you want to be notified when the alert triggers.
Logfire supports multiple notification channel types — see [Notification Channels](#notification-channels) below.

After filling in the form, click the **Create alert** button. And... Alert created! :tada:

## Notification modes

The **"Notify me when"** setting controls when you receive notifications. There are four modes:

### The query has any results

This is the default mode. You'll receive a notification **every time** the alert runs and the query returns one or more rows. This is useful for simple threshold alerts where you always want to be notified.

**Example use case:** Alert me every 5 minutes if there are any 5xx errors.

### The query starts or stops having results

You'll receive a notification when the query **transitions** between having results and not. If your query is written so that rows indicate a problem (e.g., selecting error spans), this means you'll be notified both when the issue starts and when it resolves.

**Example use case:** Alert me when my API starts experiencing high latency (over 1 second), and again when it recovers.

### The query starts having results

Same as above, but you'll **only** be notified on the transition from no rows to rows — not the other direction. If rows indicate a problem, this means you'll hear about the onset but not the resolution.

**Example use case:** Alert me when my service starts throwing exceptions, but don't notify me when it stops — I'll check resolution on my own schedule.

### The query's results change

You'll receive a notification whenever the **actual data** returned by the query changes between consecutive runs. This is more granular than the previous mode — it detects changes in the result set itself, not just whether there are results.

**Example use case:** Detect when a service goes down by querying for health check spans and [using a `CASE` expression](../../how-to-guides/detect-service-is-down.md) to return `'up'` or `'down'`. You'll be notified when the status changes in either direction.

## Alert History

After creating an alert, you'll be redirected to the alerts' list. There you can see the alerts you've created and their status.

If the query was not matched in the last time window, you'll see **no matches** next to the alert name, and no results in the histogram table of the selected time period.

![Alerts list](../../images/guide/browser-alerts-no-error.png)

Otherwise, you'll see the number of matches highlighted in orange.

![Alerts list with error](../../images/guide/browser-alerts-error.png)

In this case, you'll also receive a notification in the Webhook URL you've set up.

## Edit an alert

You can configure an alert by clicking on the **Configuration** button on the right side of the alert.

![Edit alert](../../images/guide/browser-alerts-edit.png)

You can update the alert, or delete it by clicking the **Delete** button. If instead of deleting the alert, you want to disable it, you can click on the **Active** switch.

## Notification Channels

Notification channels define where and how alerts are delivered. You can manage channels from the **Channels** tab in the Alerts section. Each channel is configured once and can be reused across multiple alerts.

Logfire supports the following channel types:

### Automatic Detection (Auto)

Sends a POST request to a URL and auto-detects the appropriate payload format based on the URL (e.g., Slack webhooks are detected automatically). Use this if you're not sure which webhook format to use, or if you want Logfire to pick the best format.

### Slack

Sends a richly formatted message using Slack's [Block Kit](https://api.slack.com/block-kit) format. This is the recommended format for Slack webhooks.

??? tip "Get a Slack webhook URL"
    To get a Slack webhook URL, follow the instructions in the [Slack documentation](https://api.slack.com/messaging/webhooks).

Configure the channel by entering your Slack **Incoming Webhook URL**.

### Slack (Legacy) / Discord

Sends a simpler webhook payload in the older Slack format. This format is also compatible with **Discord** [webhook integrations](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks), which accept the legacy Slack payload shape.

Configure the channel by entering your webhook URL.

### Opsgenie

Sends an alert to [Opsgenie](https://www.atlassian.com/software/opsgenie). This is useful for on-call workflows and incident management.

Configure the channel with:

- **Auth Key**: Your Opsgenie API integration key.
- **Base URL** (optional): Override the Opsgenie API base URL, for example if you use Opsgenie EU (`https://api.eu.opsgenie.com`). Defaults to the standard US endpoint.

### Webhook

Sends a POST request with a JSON payload containing the raw alert result data. Use this to integrate with custom systems or build your own notification pipeline.

## Notification Schedules

Schedules let you restrict when alert notifications are delivered, so you only get paged during the hours that matter.

A schedule defines:

- **Days of the week** on which notifications are active.
- **Start time** and **end time** (in the configured timezone) during which notifications can be sent.
- **Timezone** — IANA timezone name (e.g. `America/New_York`, `Europe/London`).

If an alert fires outside the scheduled window, the notification is suppressed for that run. Alerts still run and their results are recorded; only the delivery is gated.

Schedules are managed from the **Schedules** tab on the Delivery page and can be attached to any notification channel.