# Dashboards

This guide explains how to use dashboards in the Logfire UI to visualize your observability data. Dashboards let you define custom visualizations using SQL queries.

---

## Overview

There are two types of dashboards:

* **Standard dashboards**: Pre-configured dashboards created and maintained by the Logfire team. You can enable them in your project, but you can't modify them directly.
* **Custom dashboards**: Dashboards created by you. Fully editable and customizable using the UI. You can define queries, layout, chart types, and variables.

The easiest way to get started with dashboards is to enable a standard one.

---

## Enabling a Standard Dashboard

To enable a standard dashboard:

1. Go to the **Dashboards** tab in the top navigation bar.
2. Click the **+ Dashboard** button.
3. Browse the list of available dashboards under the "Standard" tab.
4. Click **Enable dashboard** to activate one in your project.

You can view and interact with standard dashboards, but you cannot edit them. These dashboards may change over time as we improve the performance of the panels inside them.

### Using a Standard Dashboard as a Template

You can export any standard dashboard and import it using the "Import JSON" feature to use the standard dashboard as a template:

1. Within a standard dashboard view, click **Download dashboard as code** on the toolbar below the dashboard name (it's the second icon from right to left).
2. Select the **Custom** tab and then select the **Import JSON** sub-tab.
3. Import the file you just downloaded, and you will be able to modify this dashboard.

---

## Creating and Editing Custom Dashboards

To create a dashboard:

1. Click the **+ Dashboard** button.
2. Select the **Custom** tab.
3. After creating your dashboard you can start adding panels. by clicking the **Panel** button on the top right.

You can rearrange and resize panels using drag-and-drop after clicking the **Edit layout** button

### Chart Types

Logfire supports these chart types:

| Chart Type  | Query Type         | Description                          |
| ----------- | ------------------ | ------------------------------------ |
| Time Series | TimeSeriesQuery    | Line charts over time                |
| Gauge       | TimeSeriesQuery    | Shows current value as a gauge       |
| Table       | NonTimeSeriesQuery | Tabular data with rows and columns   |
| Bar Chart   | NonTimeSeriesQuery | Comparisons across categories        |
| Pie Chart   | NonTimeSeriesQuery | Distribution as segments of a circle |
| Values      | NonTimeSeriesQuery | Key metrics displayed as value tiles |

To configure a chart:

1. Choose the type.
2. Write your SQL query.
3. Customize formatting, labels, and appearance.

---

## Writing Queries

Logfire uses SQL to define dashboard queries.

If you're not sure what tables or columns are available, refer to the [Records schema reference](INSERT_LINK_HERE) and [Metrics schema reference](LINK).

### Variable Usage

You can reference dashboard variables inside SQL using `$variable` syntax:

```sql
SELECT * FROM records WHERE service = $service_name
```

Only SQL queries can use variables. You can't use them in chart titles or elsewhere.

### Resolution Variable

All dashboards have access to a special special variable called `$resolution` into your query. This value is dynamically selected based on the dashboard's duration to ensure optimal performance and data density. You can use it for time bucketing:

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

### Types

* **Text variable**: User enters any string
* **List variable**: User picks from a static list of values

To add variables:

1. Open a custom dashboard
2. Click **Variables** on the top right to open the variables settings
3. Click **+ Add variable**
4. Add and configure your variables

Once declared, they are available for use in SQL as `$your_variable_name`

---

## Layout, Duration, and Refresh

Each dashboard can define:

* **Layout**: Panels are arranged in a grid. Drag to resize and move.
* **Duration**: Controls the time range for the data shown (e.g., 1h, 6h, 24h)
* **Refresh Interval**: Set how often the dashboard should auto-refresh

Duration and refresh settings are available in the top-right corner of the dashboard view.
