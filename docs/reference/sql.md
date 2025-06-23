# SQL

## Syntax

**Logfire** lets you query your data using SQL. The underlying database is Apache DataFusion, so the primary reference for the SQL syntax can be found in their [SQL Language Reference](https://datafusion.apache.org/user-guide/sql/index.html). However it's generally meant to match [PostgreSQL syntax](https://www.postgresql.org/docs/current/queries.html) which is easier to look up. We also extend it in various ways, particularly with [JSON functions and operators](https://github.com/datafusion-contrib/datafusion-functions-json) such as `->>`.

## Tables

Data is stored in two main tables: `records` and `metrics`.

`records` is the table you'll usually care about and is what you'll see in the Live View. Each row in `records` is a span or log (essentially a span with no duration). A _trace_ is a collection of spans that share the same `trace_id`, structured as a tree.

`metrics` contains pre-aggregated numerical data which is usually more efficient to query than `records` for certain use cases. There's currently no dedicated UI for metrics, but you can query it directly using SQL in the Explore view, Dashboards, Alerts, or the API, just like you would with `records`.

Technically `records` is a subset, the full table is called `records_full` which includes additional rows called pending spans, but you can ignore that for most use cases.
