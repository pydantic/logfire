# Dashboards

This guide explains how to use dashboards in the Logfire UI to visualize your observability data. Dashboards allow you to create custom visualizations using SQL queries.

---

## Overview

There are two types of dashboards:

* **Standard dashboards**: Pre-configured dashboards created and maintained by the Logfire team. You can enable them for your project, but you can't modify them directly.
* **Custom dashboards**: Dashboards that you create. They are fully editable and customizable, allowing you to define queries, layouts, chart types, and variables.

The easiest way to get started with dashboards is to enable a standard one.

---

## Standard Dashboards

Pre-built dashboards managed by the **Logfire** team.

### Web Server Metrics

This dashboard gives an overview of how long each of your web server endpoints takes to respond to requests and how often they succeed and fail. It relies on the standard OpenTelemetry http.server.duration metric which is collected by many instrumentation libraries, including those for FastAPI, Flask, Django, ASGI, and WSGI. Each chart is both a timeline and a breakdown by endpoint. Hover over each chart to see the most impactful endpoint at the top of the tooltip. The charts show:

- **Total duration:** Endpoints which need to either be optimized or called less often.
- **Average duration:** Endpoints which are slow on average and need to be optimized.
- **2xx request count:** Number of successful requests (HTTP status code between 200 and 299) per endpoint.
- **5xx request count:** Number of server errors (HTTP status code of 500 or greater) per endpoint.
- **4xx request count:** Number of bad requests (HTTP status code between 400 and 499) per endpoint.

### Basic System Metrics

This dashboard shows essential system resource utilization metrics. It comes in two variants:

- **Basic System Metrics (Logfire):** Uses the data exported by [`logfire.instrument_system_metrics()`](../../integrations/system-metrics.md).
- **Basic System Metrics (OpenTelemetry):** Uses data exported by any OpenTelemetry-based instrumentation following the standard semantic conventions.

Both variants include the following metrics:

* **Number of Processes:** Total number of running processes on the system.
* **System CPU usage %:** Percentage of total available processing power utilized by the whole system, i.e. the average across all CPU cores.
* **Process CPU usage %:** CPU used by a single process, where e.g. using 2 CPU cores to full capacity would result in a value of 200%.
* **Memory Usage %:** Percentage of memory currently in use by the system.
* **Swap Usage %:** Percentage of swap space currently in use by the system.

### Enabling a Standard Dashboard

To enable a standard dashboard:

1. Go to the **Dashboards** tab in the top navigation bar.
2. Click the **+ Dashboard** button.
3. Browse the list of available dashboards under the **Standard** tab.
4. Click **Enable dashboard** to add it to your project.

You can view and interact with standard dashboards, but you cannot edit them.

### Using a Standard Dashboard as a Template

You can use any standard dashboard as a template by exporting it and then importing it as a custom dashboard.

1. From a standard dashboard, click the **Download dashboard as code** icon in the toolbar.
2. Go to the **Custom** tab and select the **Import JSON** option.
3. Import the file you downloaded. This creates a new, fully editable custom dashboard from the template.

---

## Creating custom dashboards

To create a dashboard from scratch:

1. Click the **+ Dashboard** button.
2. Select the **Custom** tab.

Custom dashboards are structured in a hierarchy: a dashboard contains one or more **panel groups**, and each group contains **panels**. Each panel, in turn, holds a specific **chart type**. By default, new dashboards start with one panel group.

You can add more panel groups to better organize your dashboard. This is useful for grouping related visualizations, effectively allowing you to have multiple views within a single dashboard.

To add a new group, click the **Panel Group** button in the top right. You can name the group and set whether it should be expanded or collapsed by default when the dashboard loads.

To add a new visualization, you add a panel to a group. Click the **Panel** button in the top right. Inside each panel, you'll configure a chart and the SQL query that powers it.

You can rearrange and resize panels by dragging and dropping them after clicking the **Edit layout** button.

### Chart Types

Logfire supports these chart types:

| Chart Type  | Query Type         | Description                          |
| ----------- | ------------------ | ------------------------------------ |
| Time Series | TimeSeriesQuery    | Data points over time                |
| Gauge       | TimeSeriesQuery    | Shows current value as a gauge       |
| Table       | NonTimeSeriesQuery | Tabular data with rows and columns   |
| Bar Chart   | NonTimeSeriesQuery | Comparisons across categories        |
| Pie Chart   | NonTimeSeriesQuery | Data as slices of a circle |
| Values      | NonTimeSeriesQuery | Values displayed as tiles |

!!! note
    Queries with `TimeSeriesQuery` as the **Query Type** must return a timestamp column.

To configure a chart:

1. Choose the chart type.
2. Write your SQL query.
3. Customize the formatting, labels, and appearance.

---

## Writing Queries

Logfire uses SQL to define dashboard queries.

If you're unsure which tables or columns are available, refer to the [records schema](explore.md#records-schema) and [metrics schema](explore.md#metrics-schema).

### Variable Usage

You can reference dashboard variables in SQL queries using the `$variable` syntax:

```sql
SELECT * FROM records WHERE service = $service_name
```

Variables can only be used in SQL queries. They cannot be used in chart titles or other non-query fields.

### Resolution Variable

All dashboards have access to a special `$resolution` variable that can be used in your queries. This value is dynamically selected based on the dashboard's time duration to ensure optimal performance and data density. You can use it for time bucketing:

```sql
SELECT
  time_bucket($resolution, start_timestamp) AS x,
  count(1) as count
FROM records
GROUP BY x;
```

---

## Variables

You can define variables to make dashboards dynamic.

### Variable Types

* **Text variable**: Allows users to enter any string value.
* **List variable**: Allows users to select a value from a predefined list.

To add variables to a custom dashboard:

1. Open the dashboard you want to edit.
2. Click **Variables** in the top right to open the variable settings panel.
3. Click **+ Add variable**.
4. Define and configure your variables.

Once defined, variables can be referenced in SQL queries using the format `$your_variable_name`

---

## Layout, Duration, and Refresh

Each dashboard has settings for:

* **Layout**: Panels are arranged on a grid. You can drag panels to move and resize them.
* **Duration**: Controls the time range for the data shown (e.g., 1h, 6h, 24h).
* **Refresh Interval**: Sets how often the dashboard automatically refreshes its data.

The duration and refresh settings are in the top-right corner of the dashboard view.
