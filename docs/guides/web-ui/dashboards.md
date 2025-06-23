# Dashboards

This guide illustrates how to create and customize dashboards within the **Logfire UI**, thereby enabling effective
monitoring of services and system metrics.

![Logfire Dashboard](../../images/guide/browser-dashboard.png)

## Get started

**Logfire** provides several pre-built dashboards as a convenient starting point.

## Web Server Metrics

This dashboard gives an overview of how long each of your web server endpoints takes to respond to requests and how often they succeed and fail.
It relies on the standard OpenTelemetry `http.server.duration` metric which is collected by many instrumentation libraries, including those for FastAPI, Flask, Django, ASGI, and WSGI. Each chart is both a timeline and a breakdown by endpoint. Hover over each chart to see the most impactful endpoint at the top of the tooltip. The charts show:

- **Total duration:** Endpoints which need to either be optimized or called less often.
- **Average duration:** Endpoints which are slow on average and need to be optimized.
- **2xx request count:** Number of successful requests (HTTP status code between 200 and 299) per endpoint.
- **5xx request count:** Number of server errors (HTTP status code of 500 or greater) per endpoint.
- **4xx request count:** Number of bad requests (HTTP status code between 400 and 499) per endpoint.

## Basic System Metrics

This dashboard shows essential system resource utilization metrics. It comes in two variants:

- **Basic System Metrics (Logfire):** Uses the data exported by [`logfire.instrument_system_metrics()`](../../integrations/system-metrics.md).
- **Basic System Metrics (OpenTelemetry):** Uses data exported by any OpenTelemetry-based instrumentation following the standard semantic conventions.

Both variants include the following metrics:

* **Number of Processes:** Total number of running processes on the system.
* **System CPU usage %:** Percentage of total available processing power utilized by the whole system, i.e. the average across all CPU cores.
* **Process CPU usage %:** CPU used by a single process, where e.g. using 2 CPU cores to full capacity would result in a value of 200%.
* **Memory Usage %:** Percentage of memory currently in use by the system.
* **Swap Usage %:** Percentage of swap space currently in use by the system.

## Custom Dashboards

To create a custom dashboard, follow these steps:

1. From the dashboard page, click on the "Start From Scratch" button.
3. Once your dashboard is created, you can start rename it and adding charts and blocks to it.
4. To add a chart, click on the "Add Chart" button.
5. Choose the type of block you want to add.
6. Configure the block by providing the necessary data and settings (check the next section).
7. Repeat steps 4-6 to add more blocks to your dashboard.
8. To rearrange the blocks, enable the "Edit Mode" in the dashboard setting and simply drag and drop them to the desired position.

Feel free to experiment with different block types and configurations to create a dashboard that suits your monitoring needs.

## Choosing and Configuring Dashboard's Charts

When creating a custom dashboard or modifying them in Logfire, you can choose from different chart types to visualize your data.

![Logfire Dashboard chart types](../../images/guide/browser-dashboard-chart-types.png)

### Define Your Query
In the second step of creating a chart, you need to input your SQL query. The Logfire dashboard's charts grab data based on this query. You can see the live result of the query on the table behind your query input. You can use the full power of PostgreSQL to retrieve your records.

![Logfire Dashboard chart query](../../images/guide/browser-dashboard-chart-sql-query.png)

### Chart Preview and configuration

Based on your need and query, you need to configure the chart to visualize and display your data:

#### Time Series Chart

A time series chart displays data points over a specific time period.

#### Pie Chart

A pie chart represents data as slices of a circle, where each slice represents a category or value.

#### Table

A table displays data in rows and columns, allowing you to present tabular data.

#### Values

A values chart displays a single value or multiple values as a card or panel.

#### Categories

A categories chart represents data as categories or groups, allowing you to compare different groups.

## Tips and Tricks

### Enhanced Viewing with Synchronized Tooltips and Zoom

For dashboards containing multiple time-series charts, consider enabling "Sync Tooltip and Zoom." This powerful feature provides a more cohesive viewing experience:

**Hover in Sync:** When you hover over a data point on any time-series chart, corresponding data points on all synchronized charts will be highlighted simultaneously. This allows you to easily compare values across different metrics at the same time point.
**Zooming Together:** Zooming in or out on a single chart will automatically apply the same zoom level to all synchronized charts. This helps you maintain focus on a specific time range across all metrics, ensuring a consistent analysis.
Activating Sync

To enable synchronized tooltips and zoom for your dashboard:

* Open your dashboard in Logfire.
* Click on Dashboard Setting
* activate "Sync Tooltip and Zoom" option.

### Customizing Your Charts

**Logfire** empowers you to personalize the appearance and behavior of your charts to better suit your needs.
Here's an overview of the available options:

* **Rename Chart:** Assign a clear and descriptive title to your chart for improved readability.
* **Edit Chart**: Change the chart query to better represent your data.
* **Duplicate Chart:** Quickly create a copy of an existing chart for further modifications, saving you time and effort.
* **Delete Chart:** Remove a chart from your dashboard if it's no longer relevant.
