---
title: "Logfire Alerts: Status Monitoring & Error Notifications"
description: "Learn how to create alerts based on SQL query conditions (e.g., error count threshold). Use Logfire to track status changes and send notifications to Slack."
---
With **Logfire**, use Alerts to notify you when certain conditions are met.

![Logfire alerts screen](../../images/guide/browser-alerts-full.png)

## Create an alert

Let's see in practice how to create an alert.

1. Go to **Alerts** in the **Notify** section of the left sidebar.
2. Click the **New alert** button.
3. Pick **Custom query** (or start from one of the templates).

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

Under **When this alert fires** you can pick the firing condition (**Fire when**), the time range over which the query is executed (**Look at rows from**), and how often it runs (**Check every**).

The **Send notifications to** section is where you choose which delivery channels receive a notification when the alert fires — Slack, Opsgenie, or a generic webhook endpoint. Click **Add channel** to create one inline, or manage them centrally as described in [Delivery channels and schedules](#delivery-channels-and-schedules) below. An alert without channels still shows up on the Alerts page — it just won't ping anyone outside **Logfire**.

??? tip "Get a Slack webhook URL"
    To get a Slack webhook URL, follow the instructions in the [Slack documentation](https://api.slack.com/messaging/webhooks), or see our [Slack alerts setup guide](../../how-to-guides/setup-slack-alerts.md).

After filling in the form, click the **Create alert** button. And... Alert created! :tada:

## Notification modes

The **Fire when** setting (under **When this alert fires**) controls when you receive notifications. There are four modes:

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

## Delivery channels and schedules

Channels and schedules are managed under **Delivery** in the **Notify** section of the left sidebar, on the **Channels** and **Schedules** tabs. Channels are shared across all projects in your organization.

### Channels

Click **New channel** to create a channel (you can also do this inline from the alert form with **Add channel**). Give it a name and pick a type:

- **Auto** — a webhook where **Logfire** infers the payload format from the URL: Slack [Block Kit](https://api.slack.com/block-kit) for `hooks.slack.com` URLs, raw JSON data for `hooks.zapier.com` URLs, and a legacy [Slack format] payload for anything else. Discord webhook URLs work out of the box — **Logfire** automatically appends `/slack` so Discord accepts the Slack-format payload.
- **Slack Webhook** — always sends Slack Block Kit payloads.
- **Slack Legacy (for Discord, etc.)** — always sends legacy Slack-format payloads, which services other than Slack (such as Discord) also accept.
- **Opsgenie** — sends alerts to the Opsgenie Alert API using an authorization key, with an optional custom base URL (e.g. `https://api.eu.opsgenie.com`).
- **Webhook** — sends the raw alert data as JSON, for custom integrations.

The **Test your channel** section lets you verify the configuration before saving: pick an alert variant, then click **Send a test alert** to deliver a sample notification to the channel. A successful test is required before you can create a webhook or Opsgenie channel (or change its URL or key). **Copy sample JSON payload** copies the exact JSON body **Logfire** would send for the selected variant, so you can build a custom receiver against it.

### Schedules

Schedules define time windows for alert notification delivery — for example, business hours only. A schedule has a timezone and one or more weekly windows (days of the week plus a start and end time). Create them on the **Schedules** tab with **New schedule**.

On the alert form, each selected channel can be assigned a schedule (the default is **Always deliver**). Notifications triggered outside the configured delivery windows are dropped — they are not queued or deferred.

## Alert History

After creating an alert, you'll be redirected to the alerts' list. There you can see the alerts you've created and their status.

If the query was not matched in the last time window, you'll see **no matches** next to the alert name, and no results in the histogram table of the selected time period.

![Alerts list](../../images/guide/browser-alerts-no-error.png)

Otherwise, you'll see the number of matches highlighted in orange.

![Alerts list with error](../../images/guide/browser-alerts-error.png)

In this case, you'll also receive a notification on the channels you've set up.

## Edit an alert

You can configure an alert by clicking on the **Configuration** button on the right side of the alert.

![Edit alert](../../images/guide/browser-alerts-edit.png)

You can update the alert, or delete it by clicking the **Delete** button. If instead of deleting the alert, you want to disable it, you can click on the **Active** switch.

[Slack format]: https://api.slack.com/reference/surfaces/formatting
