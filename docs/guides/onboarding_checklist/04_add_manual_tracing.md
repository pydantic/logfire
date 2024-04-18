In the previous sections, we focused on how to integrate Logfire with your application and leverage automatic
instrumentation. In this section, we'll go into more detail about manual tracing, which allows you to add custom spans
and logs to your code for targeted data collection.

Because the specifics of where and how to add manual tracing will depend on your particular application, we'll also
spend time discussing the general principles and scenarios where manual tracing can be especially valuable.

## How to Add Manual Tracing

### Using the `@logfire.instrument` Decorator

The [`@logfire.instrument`][logfire.Logfire.instrument] decorator is a convenient way to create a span around an entire function. To use it, simply
add the decorator above the function definition:

```python
@logfire.instrument("Function Name", extract_args=True)
def my_function(arg1, arg2):
# Function code
```

The first argument to the decorator is the name of the span, and you can optionally set `extract_args=True` to
automatically log the function arguments as span attributes.

!!! note

    - The [`@logfire.instrument`][logfire.Logfire.instrument] decorator MUST be applied first, i.e., UNDER any other decorators.
    - The source code of the function MUST be accessible.

### Creating Manual Spans

To create a manual span, use the [`logfire.span`][logfire.Logfire.span] context manager:

```python
with logfire.span("Span Name", key1=value1, key2=value2):
    # Code block
    logfire.info("Log message", key3=value3)
```

The first argument is the name of the span, and you can optionally provide key-value pairs to include custom data in the
span.

### Nesting Spans

You can nest spans to create a hierarchical structure:

```python
with logfire.span("Outer Span"):
    # Code block
    with logfire.span("Inner Span"):
        # Code block
        logfire.info("Log message")
```

When nesting spans, try to keep the hierarchy clean and meaningful, and use clear and concise names for your spans.

### Recording Custom Data

To record custom data within a span, simply pass key-value pairs when creating the span or when logging messages:

```python
with logfire.span("User Login", user_id=user_id):
    logfire.info("User logged in", user_email=user_email)
```

Consider recording data that will be useful for debugging, monitoring, or analytics purposes.

### Capturing Exceptions

Logfire automatically captures exceptions that bubble up through spans. To ensure that exceptions are properly captured
and associated with the relevant span, make sure to wrap the code that may raise exceptions in a span:

```python
with logfire.span("Database Query"):
    try:
        result = db.query(query)
    except DatabaseError as e:
        logfire.error(f"Database query failed: {str(e)}")
        raise
```

## When to Use Manual Tracing

Now that we've seen how to use manual tracing, let's discuss some scenarios where manual tracing can be particularly
useful in enhancing your application's observability:

### Scenario 1: Improving Log Organization and Readability

When working with complex functions or code blocks, manually nested spans can help organize your logs into a
hierarchical structure. This makes it easier to navigate and understand the flow of your application, especially during
debugging sessions.

```python
import logfire


@logfire.instrument("Complex Operation")
def complex_operation(data):
    # Step 1
    with logfire.span("Data Preprocessing"):
        preprocessed_data = preprocess(data)
        logfire.info("Data preprocessed successfully")

    # Step 2
    with logfire.span("Data Analysis"):
        analysis_result = analyze(preprocessed_data)
        logfire.info("Analysis completed")

    # Step 3
    with logfire.span("Result Postprocessing"):
        final_result = postprocess(analysis_result)
        logfire.info("Result postprocessed")

    return final_result
```

In this example, the `complex_operation` function is decorated with [`@logfire.instrument`][logfire.Logfire.instrument],
which automatically creates a span for the entire function. Additionally, the function is broken down into three main steps,
each wrapped in its own span, and you can imagine that the functions called in each of these sections might each produce
various spans as well. This creates a clear hierarchy in the logs, making it easier to identify and focus on relevant
sections during debugging.

[TODO: Include a screenshot of the web UI showing the hierarchical structure of spans]

### Scenario 2: Measuring Execution Duration

Manual spans can be used to measure the duration of specific code sections, helping you identify performance bottlenecks
and detect regressions.

```python
import logfire


@logfire.instrument("Process Data Batch", extract_args=True)
def process_data_batch(batch):
    # Process the data batch
    processed_data = []
    for item in batch:
        with logfire.span("Process Item {item}"):
            item = step_1(item)
            item = step_2(item)
            item = step_3(item)
        processed_data.append(item)

    return processed_data
```

In this example, the process_data_batch function is decorated with `@logfire.instrument`, which automatically creates a
span for the entire function and logs the batch argument as a span attribute.

Additionally, each item in the batch is processed within a separate span created using the [`logfire.span`][logfire.Logfire.span] context
manager. The span name includes the item being processed, providing more granular visibility into the processing of
individual items.

By using manual spans in this way, you can measure the duration of the overall data batch processing, as well as the
duration of processing each individual item. This information can be valuable for identifying performance bottlenecks
and optimizing your code.

[Include a screenshot of the web UI showing the duration of the Process Data Batch span and the individual Process Item spans]

### Scenario 3: Capturing Exception Information

Logfire automatically captures full stack traces when exceptions bubble up through spans. By strategically placing spans
around code that may raise exceptions, you can ensure that you have the necessary context and information for debugging
and error monitoring.

```python
import logfire


@logfire.instrument("Fetch Data from API", extract_args=True)
def fetch_data_from_api(api_url):
    response = requests.get(api_url)
    response.raise_for_status()
    data = response.json()
    logfire.info("Data fetched successfully")
    return data
```

If an exception occurs while fetching data from the API, Logfire will capture the stack trace and associate it with the
span created by the `@logfire.instrument` decorator. The `api_url` argument will also be logged as a span attribute,
providing additional context for debugging.

[TODO: Include a screenshot of the web UI showing the exception details, stack trace, and `api_url` attribute]

### Scenario 4: Recording User Actions and Custom Data

Manual spans can be used to record user actions, input parameters, or other custom data that may be valuable for
analytics and business intelligence purposes.

```python
import logfire


def search_products(user_id, search_query, filters):
    with logfire.span(f"Performing search: {search_query}", search_query=search_query, filters=filters):
        results = perform_search(search_query, filters)

    if not results:
        logfire.info("No results found for search query", search_query=search_query)
        with logfire.span("Suggesting Related Products"):
            related_products = suggest_related_products(search_query)
        return {
            "status": "no_results",
            "related_products": related_products
        }
    else:
        logfire.info(f"Found {len(results)} results for search query", search_query=search_query)
        return {
            "status": "success",
            "results": results
        }
```

In this example, the `search_products` function is instrumented with manual spans and logs to capture user actions and
custom data related to product searches.

The function starts by creating a span named `"Performing search: {search_query}"` that measures the duration and
captures the details of the actual search operation. The `search_query` and `filters` are included as span attributes,
allowing for fine-grained analysis of search performance and effectiveness.

After performing the search, the function checks the results:

1. If no results are found, an info-level log message is recorded, indicating that no results were found for the given
   search query. Then, a `"Suggesting Related Products"` span is created, and the `suggest_related_products` function is
   called to generate a list of related products. The function returns a response with a `status` of `"no_results"` and
   the list of `related_products`. This data can be used to identify common search queries that yield no results and
   help improve the product catalog or search functionality.

2. If results are found, an info-level log message is recorded, indicating the number of results found for the search
   query. The function then returns a response with a `status` of `"success"` and the `results` list.

By structuring the spans and logs in this way, you can gain insights into various aspects of the product search
functionality:

- The `"Performing search: {search_query}"` span measures the duration of each search operation and includes the
  specific search query and filters, enabling performance analysis and optimization.
- The info-level log messages indicate whether results were found or not, helping to identify successful and
  unsuccessful searches.
- The `"Suggesting Related Products"` span captures the process of generating related product suggestions when no
  results are found, providing data for analyzing and improving the suggestion algorithm.

[TODO: Include a screenshot of the web UI showing the spans and custom data logged during a product search]

This example demonstrates how manual spans and logs can be strategically placed to capture valuable data for analytics
and business intelligence purposes.

Some specific insights you could gain from this instrumentation include:

- Identifying the most common search queries and filters used by users, helping to optimize the search functionality and
  product catalog.
- Measuring the performance of search operations and identifying potential bottlenecks or inefficiencies.
- Understanding which search queries frequently result in no results, indicating areas where the product catalog may
  need to be expanded or the search algorithm improved.
- Analyzing the effectiveness of the related product suggestion feature in helping users find relevant products when
  their initial search yields no results.

By capturing this data through manual spans and logs, you can create a rich dataset for analytics and business
intelligence purposes, empowering you to make informed decisions and continuously improve your application's search
functionality and user experience.

## Best Practices and Tips

- Use manual tracing judiciously. While it can provide valuable insights, overusing manual spans can lead to cluttered
  logs and source code, and increased overhead in hot loops.
- Focus on critical or complex parts of your application where additional context and visibility will be most
  beneficial.
- Choose clear and concise names for your spans to make it easier to understand the flow and purpose of each span.
- Record custom data that will be useful for debugging, monitoring, or analytics purposes, but avoid including sensitive
  or unnecessary information.

## Conclusion

Manual tracing is a powerful tool for adding custom spans and logs to your code, providing targeted visibility into your
application's behavior. By understanding the principles and best practices of manual tracing, you can adapt this
technique to your specific use case and enhance your application's observability.

Remember to balance the benefits of detailed tracing with the overhead of adding manual spans, and focus on the areas
where additional context and visibility will be most valuable.
