# Aggregating Metrics in Spans

!!! note
    This is an experimental feature. The API and data format may change in future releases. We welcome your feedback to help us prioritize improvements and stability.

Logfire lets you aggregate counter and histogram metrics within the current active span and its ancestors. This is particularly useful for calculating totals for things like LLM token usage or costs on higher-level operations, making it easier and more efficient to query this data without processing individual child spans.

This guide will walk you through how to enable this feature and use it with both custom metrics and automated instrumentation.

## Enabling Metric Aggregation

To enable this feature, you need to configure Logfire with the `collect_in_spans` option in [`MetricsOptions`][logfire.MetricsOptions]. This should be done once when your application starts.

```py
import logfire

logfire.configure(metrics=logfire.MetricsOptions(collect_in_spans=True))
```

Once enabled, any counters or histograms recorded within a span will be aggregated into a `logfire.metrics` attribute on that span.

## Simple Example: A Custom Cost Counter

Let's start with a simple example of tracking a cumulative cost.

First, we define a metric counter. Then, within a span, we add to it multiple times.

```py
import logfire

logfire.configure(metrics=logfire.MetricsOptions(collect_in_spans=True))

counter = logfire.metric_counter('cost')

with logfire.span('spending'):
    counter.add(1)
    counter.add(2)
```

The `spending` span will now contain a `logfire.metrics` attribute that holds the aggregated total of the `cost` counter, i.e. `3`.
Running the following query in the Explore view:

```sql
SELECT attributes->>'logfire.metrics'->>'cost'->>'total' AS total_cost
FROM records
WHERE span_name = 'spending'
```

will return one row with `total_cost` equal to `3`.

## Advanced Example: LLM Token Usage with Pydantic AI

Generative AI instrumentations like Pydantic AI that follow OpenTelemetry conventions will record a metric called `gen_ai.client.token.usage`. You can use metric aggregation to get a total of tokens used in a higher-level operation that may involve multiple LLM calls.

Here’s an example:

```py
from pydantic_ai import Agent
import logfire

logfire.configure(metrics=logfire.MetricsOptions(collect_in_spans=True))
logfire.instrument_pydantic_ai()

agent = Agent('gpt-4o')

@agent.tool_plain
async def get_random_number() -> int:
    return 4

with logfire.span('span'):
    agent.run_sync('Give me one random number')
    agent.run_sync('Generate two random numbers')
```

The calls to `agent.run_sync` create child spans named `agent run`. The outer `span` aggregates the token metrics from these children, as shown in the Live View:




### Understanding the Span Data

The outer `'span'` now has a `logfire.metrics` attribute containing the aggregated token data from the two `agent.run_sync` calls. The JSON structure looks like this:

```json
{
  "gen_ai.client.token.usage": {
    "details": [
      {
        "attributes": {
          "gen_ai.operation.name": "chat",
          "gen_ai.request.model": "gpt-4o",
          "gen_ai.response.model": "gpt-4o-2024-08-06",
          "gen_ai.system": "openai",
          "gen_ai.token.type": "input"
        },
        "total": 224
      },
      {
        "attributes": {
          "gen_ai.operation.name": "chat",
          "gen_ai.request.model": "gpt-4o",
          "gen_ai.response.model": "gpt-4o-2024-08-06",
          "gen_ai.system": "openai",
          "gen_ai.token.type": "output"
        },
        "total": 73
      }
    ],
    "total": 297
  }
}
```

As you can see, the `details` array contains separate entries for `input` and `output` tokens, each with its own total.

### Querying Nested Token Data

To query these nested details, you need a more complex SQL query to "un-nest" the JSON data into a flat, table-like structure.

```sql
WITH
    with_span_metric_name AS (SELECT unnest(json_keys(attributes->>'logfire.metrics')::text[]) AS span_metric_name, * FROM records),
    with_span_metric AS (SELECT attributes->>'logfire.metrics'->>span_metric_name AS span_metric, * FROM with_span_metric_name),
    with_span_metric_detail AS (SELECT span_metric->>'details'->>unnest(generate_series((json_length(span_metric->>'details') - 1)::int)) AS span_metric_detail, * FROM with_span_metric)
SELECT
    span_name,
    span_metric_detail->>'total' AS total,
    span_metric_detail->>'attributes'->>'gen_ai.token.type' AS token_type
FROM with_span_metric_detail
WHERE span_metric_name = 'gen_ai.client.token.usage'
```

**How this query works:**

*   The `WITH` clauses progressively expand the nested JSON in the `logfire.metrics` attribute.
*   `with_span_metric_name` unnests the metric names (e.g., `'gen_ai.client.token.usage'`).
*   `with_span_metric` extracts the JSON object for each metric.
*   `with_span_metric_detail` unnests the `details` array, creating a separate row for each item (one for `input` and one for `output` in our example).

You can copy the `WITH` clauses as a reusable prefix for any query that needs to analyze aggregated metrics. The final `SELECT` statement then easily extracts the total tokens for each type.

The result of this query will look like this, showing token counts broken down by span and type:



## Limitations and Caveats

Please keep the following points in mind when using this experimental feature:

*   **API Instability**: As an experimental feature, the API and the underlying data format may change.
*   **Complex Queries**: Querying nested metrics currently requires complex SQL, as shown above. We plan to simplify this in the future.
*   **No Special UI Support**: The Logfire UI does not yet have special features for visualizing these aggregated metrics beyond the token badge. They are primarily accessible via the `attributes` field and SQL queries.
*   **Process-Scoped**: Aggregation only occurs for metrics collected within the same process. It does not work across distributed traces that span multiple services or processes.
*   **No Automatic Cost Calculation**: The feature aggregates token counts but does not automatically calculate the associated monetary cost.