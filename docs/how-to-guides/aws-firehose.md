---
title: Send AWS logs and metrics through Firehose
description: Stream CloudWatch logs and metrics to Logfire with a CloudFormation template and verify delivery.
---

Send new CloudWatch logs and metric samples to a Logfire project without running a collector.
Amazon Data Firehose buffers the data and delivers it to Logfire over HTTPS.

!!! warning "Experimental"
    The Cloud onboarding guide is available in staging and local development.
    Your Logfire deployment must enable Firehose ingestion.
    Confirm support for both selected signals with your administrator before you create resources.
    This guide does not enable Firehose on your deployment.

## Before you start

You need:

- A Logfire project and a service write token for the project.
  A project administrator can use the Cloud guide to create an ingest-only service API key.
  For manual setup, create a token under **Settings → Write tokens**, or an API key with the
  `project:write_otlp` scope under **Settings → API keys**.
  Ask an administrator to create the key without the personal-key option.
  A personal API key stops working if its owner loses project access.
- The deployment's public HTTPS ingest base URL, without a path or trailing slash.
- An AWS account and region that contain the data you want to collect.
- Permission to create a CloudFormation stack, Identity and Access Management (IAM) roles,
  Firehose delivery streams, CloudWatch subscriptions and metric streams, delivery log groups and streams, and an Amazon S3 bucket.
  Your identity or CloudFormation execution role also needs `iam:PassRole` for the roles passed to these services.
- For logs, an existing CloudWatch log group with an available subscription filter slot.
- For metrics, a CloudWatch namespace to collect, such as `AWS/EC2`.
  A namespace groups related metrics from one AWS service or application.

AWS collection, delivery, storage, and network traffic can incur charges.
Logfire also charges for ingested data.
Start with one log group and one metric namespace.
The template forwards all new events from the selected log group to Logfire.
It does not redact or filter their contents. Review sensitive data and sanitize it at the source before you enable collection.
Avoid collecting the same metrics through both Firehose and an OpenTelemetry Collector.

## Create the AWS resources

1. In Logfire, open **Infrastructure → Cloud → AWS** when the experimental guide is available.
   If data is already arriving, click **Set up cloud provider** at the top right, then select **AWS**.
   Select **Direct Firehose** to send logs and metrics without a Collector.
   **CloudWatch API** and **Firehose via Collector** use your own OpenTelemetry Collector.
2. To create a token, click **Create write token**. Logfire creates a dedicated key that can only send data to this project and copies it.
   If copying fails, copy the visible token. Save it before leaving the Logfire page.
   To use an existing project write token, clear **Create a dedicated write token for Firehose** and keep that token ready instead.
   Click **Launch in AWS** to open CloudFormation.
   The endpoint, setup ID, and logs-and-metrics default are filled in.
3. In AWS, choose the source account and region. Review these parameters:

   | Parameter | Value |
   | --- | --- |
   | `LogfireEndpoint` | The public HTTPS ingest base URL. The template appends the signal path. |
   | `LogfireWriteToken` | Paste the generated or existing project write token, without `Bearer `. |
   | `CollectionMode` | Keep `LogsAndMetrics`, or choose `Logs` or `Metrics` here. |
   | `LogGroupName` | The existing log group, required when you select logs. |
   | `MetricNamespace` | One namespace to collect, required when you select metrics. |
   | `SetupId` | Keep the ID supplied by the guide. Use a distinct ID for a manual setup. |

4. Acknowledge the IAM resources and create the stack. Wait for `CREATE_COMPLETE`.

Logfire shows a generated token once. Keep the token until you create the stack.
CloudFormation does not prefill secret parameters from a quick-create link.
Paste the token into its masked field in AWS.
Organization lifetime policies apply to generated tokens. Update the stack when you rotate an expiring token.

For a manual setup, expand **Manual setup and template details** to download the template.
Open CloudFormation and choose **Create stack → With new resources → Upload a template file**.
The downloaded file contains the endpoint and setup ID. It does not contain a token.

You can also [download the unconfigured version 1 template](https://s3.us-east-1.amazonaws.com/pydantic-logfire-templates-dev-e9ec7424/firehose/v1/51c9d30f52b1dbbc112d4b6d0bf5eb6168a6ad8d7d2b17b40728d305994106f1.json).
Enter the endpoint and a distinct setup ID yourself when you use this file.
CloudFormation masks the write token with `NoEcho`.
Enter the token only in AWS. Do not put it in a launch URL or source control.

The stack creates a delivery stream for each selected signal.
It subscribes the selected log group and creates a JSON metric stream for the selected namespace.
It does not include metrics from linked AWS accounts.
The delivery streams use GZIP, a 1 MiB buffer, a 60-second buffer interval, and a 300-second retry window.
Keep log decompression, message extraction, and Lambda transformations disabled.

## Verify delivery

Create a new log event in the selected log group.
For metrics, use a resource that publishes samples in the selected namespace.
Subscriptions forward new logs only. They do not import historical logs.
Allow several minutes for collection, buffering, and delivery.

Return to the Logfire guide and click **Check for data**.
If you selected one signal in AWS, expand **Changed the data selection in AWS?** and select that signal for verification.
The guide checks for stored data from each selected signal with this setup ID.
It checks every five seconds and stops after success, an error, or ten minutes.
Use **Check again** to restart a paused or failed check.
A successful check proves receipt of data. It does not prove that every source event arrived.

The AWS overview lists services with CloudWatch metrics received through Firehose or an OpenTelemetry Collector in the last 24 hours.
It shows observed accounts, regions, metric names, and last received times.
Statistic variants count as one metric name. Custom namespaces appear separately.
The overview describes received telemetry. It does not discover every resource in your AWS account.
An idle service or a service with daily metrics can be absent from this window without a delivery failure.

Once data arrives, the page hides collection setup.
Click **Set up cloud provider** to reopen it or configure another provider.
Inside AWS setup, expand **Choose an AWS service (20 services)** for collection guidance and example metrics.
Selecting a service prefills its first namespace in the launch link and template download.
The template still forwards one namespace per stack.
When you add another namespace to an existing log setup, choose `Metrics` to avoid another log subscription.

Open Logs and Metrics to inspect the data:

- Logs retain the log group, log stream, account, and region.
- Metrics have names such as `amazonaws.com/AWS/EC2/CPUUtilization/Average`.
- Each metric point retains its namespace, metric name, statistic, and dimensions.
  A dimension identifies a source resource, such as an EC2 instance.

The JSON format provides `min`, `max`, `sum`, and `count` for each sampling window.
Logfire stores each statistic as a gauge, which is a value for that window.
It also derives `Average` as `sum / count` when the count is positive and the result is finite.
For example, a sum of 90 and a count of 3 produce an average of 30.
These four source statistics normally produce five stored data points per sample.
Additional statistics produce more points.
Logfire preserves fractional sample counts and does not infer histogram buckets or a counter interval.
Counts and trimmed counts use the dimensionless unit `1`. Percentile ranks use `%`.
Each metric point keeps the original CloudWatch unit in its `Unit` attribute.
Use these gauge values directly. Do not calculate counter rates from them.

## Troubleshooting

**No data arrives.** Check the account, region, log group, namespace, and project token.
Check each delivery stream separately in AWS.
Inspect incoming records, HTTP delivery success, data freshness, and delivery error logs.
CloudWatch metric streams must use **JSON** output for this endpoint.
Local development hostnames are not reachable from Firehose.

**AWS reports an HTTP error.** For `401` or `403`, check the write token.
For `404`, check the endpoint path and deployment support.
For `429` or `5xx`, inspect retries and the failed delivery backup.
A malformed metric document rejects its whole delivery.

**Some data arrives but records are missing.** Check Logfire ingest warnings and AWS delivery errors.
A successful HTTP response can include a partial rejection.
Check source timestamps and the selected filters.
Firehose retries can produce duplicates, so row counts are not unique source-event counts.

**The stack cannot create a log subscription.** Check whether the log group has a free subscription filter slot.
Confirm that it exists in the stack's account and region.

## Rotate credentials or stop collection

Update `LogfireWriteToken` in the stack when you rotate the project write token.
Delete the stack to stop collection.
Failed deliveries go to a private, encrypted S3 bucket and expire after 30 days.
Deleting the stack retains that bucket.
Inspect or replay failed data before you remove the retained bucket separately.
Replaying data can create duplicates.

For more control over metric selection, see [Collect cloud provider metrics](cloud-metrics.md).
For the delivery protocol, see the [AWS HTTP destination documentation](https://docs.aws.amazon.com/firehose/latest/dev/httpdeliveryrequestresponse.html).
