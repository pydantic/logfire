---
title: Delete data from a project
description: Permanently delete spans, logs, or metrics that match a SQL condition, and follow the deletion until it finishes.
---

# Delete data from a project

Remove specific data from a Logfire project after it was sent: for example, a user's personal data after an erasure request, or spans that captured a secret by mistake.

You write one SQL `DELETE` statement, preview the rows it matches, and schedule a deletion job. Logfire hides the matching rows from queries as soon as you schedule the job. Background maintenance then rewrites the stored files without those rows. The job is finished when that rewrite is done.

!!! warning "Deletion is permanent"
    Logfire cannot restore deleted rows, and you cannot cancel or undo a deletion job after you schedule it. Preview every statement before you schedule it.

Use data deletion for targeted removals. To keep less data in general, shorten the project's retention period instead.

## Before you start

- **Plan.** On Logfire Cloud, data deletion is available on the Growth and Enterprise plans. On other Cloud plans, the **Data deletion** page shows an upgrade prompt. See [pricing](https://pydantic.dev/pricing). Self-hosted Logfire is part of the [Enterprise plan](../enterprise.md), and every self-hosted deployment includes data deletion.
- **Permission.** You need the **Change project information** permission on the project, which project admins have. Without it, Logfire does not show the **Data deletion** page.
- **Web UI only.** You schedule and follow deletion jobs in the Logfire web UI. There is no public API or CLI command for data deletion.
- **Self-hosted.** Use chart 0.15.0 or later. See [Self-hosted deployments](#self-hosted-deployments).

## Write the `DELETE` statement

A deletion job takes exactly one statement of this form:

```sql
DELETE FROM <table> WHERE <condition>
```

- `<table>` is one table of the project, such as `records` (spans and logs) or `metrics`. See [SQL tables](../reference/sql.md#tables).
- `<condition>` is a SQL expression on that table's columns. It can use the same functions and JSON operators as a query in the [SQL Workbench](../guides/web-ui/explore.md).
- A `WHERE` clause is required. Logfire rejects a statement without one.
- The condition cannot contain a subquery, a join, or a `WITH` clause. To delete the traces that a query finds, run the query first, then list the trace IDs in the statement.

Examples:

```sql
-- Delete whole traces by ID. A long list of IDs is fine.
DELETE FROM records WHERE trace_id IN ('0af7651916cd43dd8448eb211c80319c', '4bf92f3577b34da6a3ce929d0e0e4736')

-- Delete the spans and logs of one user, by an internal user ID.
DELETE FROM records WHERE attributes->>'user.id' = '8412'

-- Delete one service's data in one environment, from before a date.
DELETE FROM records WHERE service_name = 'checkout' AND deployment_environment = 'staging' AND start_timestamp < '2026-10-01'
```

The job applies to all of the project's data in that table, across all environments and all time. To limit the deletion to an environment, add a condition on the [`deployment_environment`](../reference/sql.md#deployment_environment) column, as in the last example. To limit it to a time range, add a condition on `start_timestamp`.

If the condition evaluates to `NULL` for a row, Logfire keeps the row, like a standard SQL `DELETE`. For example, the second statement above keeps every row that has no `user.id` attribute.

!!! note "The statement stays visible"
    Logfire stores the statement and shows it in the job list on the **Data deletion** page, to every member who can open that page. Do not put more personal data in the statement than you need. To erase data about a person, find the matching trace IDs with a query in the SQL Workbench, then delete by `trace_id`.

## Preview and schedule the deletion

1. In your project, open **Settings**, then select **Data deletion** in the **Data** group.
2. Select **New delete job**.
3. Enter your statement in the **DELETE query** field, then select **Preview**.
4. Check the preview. It shows the table, the equivalent `SELECT` statement, and the number of rows that the statement matches across all time and environments. To look at the rows themselves, select **Open in Explore**. If Logfire cannot count the rows, you can still schedule the job, but check the rows in Explore first.
5. Type `DELETE` in the **Type DELETE to confirm** field.
6. Select **Schedule deletion**.

If you change the statement after the preview, preview it again before you schedule it.

## What happens after you schedule a job

1. **The rows disappear from queries at once.** Queries on the table stop returning the matching rows.
2. **Background maintenance removes the rows from storage.** Logfire rewrites each stored file that contains matching rows, without those rows. Files that cannot contain a match are cleared without a rewrite.
3. **The job finishes.** When maintenance has processed every file, the job status changes to **Finished**.

The job deletes the matching rows that Logfire had stored when you scheduled it. Rows that arrive later are not deleted, even if they match. To delete them too, schedule another job after they arrive.

The time a job takes depends on how much data the project has in that table, not on how many rows match.

## Follow a job's progress

The **Data deletion** page lists the project's jobs with their statement, status, and creation and update times. The list refreshes every 10 seconds.

- **Running (N%)**: N is the share of the project's files in that table, counted when you scheduled the job, that maintenance has processed. Progress can move in large steps, because maintenance processes files in batches.
- **Finished**: maintenance has removed the matching rows from storage.

## Plan your deletions

- **Combine requests into one job.** Each job makes maintenance process all of the project's data in the table again. If you receive several erasure requests in a week, collect them and schedule one job per period. A long `trace_id IN (...)` list or several conditions joined with `OR` in one job is better than many small jobs.
- **Let each job finish before you schedule the next one.** Jobs that overlap make maintenance do the same work more than once.
- **Run the query first.** Before you write the statement, run the equivalent `SELECT` in the SQL Workbench and check the result.

## Self-hosted deployments

Data deletion works the same way on a self-hosted deployment, with these additions:

- **Use chart 0.15.0 or later.** In earlier chart versions, background maintenance rewrites only the last 3 days of data. A job that matches older data stays at **Running** with a partial percentage and never finishes. The matching rows are still hidden from queries. Earlier chart versions also never finish a job whose condition uses the `day` or `project_id` column. After you upgrade to 0.15.0 or later, jobs that were stuck continue and finish without any action. See [Upgrades](../reference/self-hosted/overview.md#upgrades).
- **Do not delete data by hand.** Never delete rows from the `ff` database or objects from the object storage bucket to remove telemetry. The `ff` database records which objects in the bucket hold live data. A manual change breaks that record, and Logfire cannot repair it. Use a deletion job.

## Verify the deletion

After you schedule the job, run the preview's `SELECT` statement in the SQL Workbench. It returns no rows, because Logfire hides the matching rows at once. The only exception is matching rows that arrived after you scheduled the job. The job then reaches **Finished** on the **Data deletion** page when maintenance has removed the rows from storage.

## Troubleshooting

Preview errors start with **Invalid deletion query**, followed by the reason.

- **The reason says that `DELETE` requires a `WHERE` clause.** Add a `WHERE` clause. Logfire does not delete a whole table.
- **The reason says that the statement is not a `DELETE` statement.** The statement must start with `DELETE FROM`. Logfire does not accept a `SELECT`.
- **The reason names a subquery, a join, or an unknown column.** Remove the subquery or join and list the values directly, and check the column names against [SQL tables](../reference/sql.md#tables).
- **A self-hosted job stays at Running with the same percentage.** Check the chart version. Earlier than 0.15.0, maintenance never reaches data older than 3 days. Upgrade the chart. The job then continues by itself.
- **Matching rows appear again after the job.** These rows arrived after you scheduled the job. Schedule another job for them.
