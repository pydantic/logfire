# Extracting Dataset Cases From Logfire Traces

Every project instruments differently, so nothing here assumes span names, attribute keys, or
payload shapes. Learn them from the data with the discovery sequence, then write the
extraction query.

Shape the SQL so that **one row is one case**. Always select `trace_id` and `span_id`:
they become `source_trace_id` / `source_span_id` (the case links back to its trace in
the UI) and give each case a stable name.

## Engine Rules

Logfire runs Apache DataFusion with Postgres-like syntax. It is not Postgres.

- `attributes->>'key'` returns text; `attributes->'key'` returns a JSON subtree. Chain for
  nesting: `attributes->'outer'->0->>'inner'`. Never `json_extract*`.
- Dotted attribute names are single keys: `attributes->>'some.dotted.key'`.
- List an attribute's keys with `json_object_keys(attributes)`. Get an array's length with
  `json_length(attributes->'key')`.
- Filter on `span_name`, `service_name`, `otel_scope_name`, `trace_id` and the time window
  first; they are indexed.
- One query spans at most 14 days. For more history, run several windows and merge (dedupe
  on `span_id`).
- A JSON subtree selected with `->` may arrive as a JSON-encoded string. Decode it with
  `json.loads` in the script before mapping.
- Correlated subqueries, `EXISTS` and `IN (SELECT ...)` often fail to plan. Use a CTE plus a
  `JOIN` instead.

## Discovery Sequence

Run these before writing the extraction query, and read the results. Never guess span names
or attribute keys.

**1. Inventory what produces spans.** Find the span whose lifetime brackets one unit of the
behaviour the dataset is about. Root spans (`parent_span_id IS NULL`) are a good first view;
drop that filter if the unit of work is nested.

```sql
SELECT service_name, otel_scope_name, span_name, count(*) AS n,
       min(start_timestamp) AS first_seen, max(start_timestamp) AS last_seen
FROM records
WHERE kind = 'span'
GROUP BY service_name, otel_scope_name, span_name
ORDER BY n DESC
LIMIT 40
```

When the inventory doesn't make the target obvious, search the content the user described.
`message` has a full-text index (`text_contains('keyword', message)`). A text search over
`attributes::text` works but is slow, so keep the window narrow.

**2. List the chosen span's attributes and how often each is populated.**

```sql
SELECT json_object_keys(attributes) AS keys
FROM records
WHERE span_name = '<chosen span>'
ORDER BY start_timestamp DESC
LIMIT 3
```

```sql
SELECT count(*) AS n,
       count(*) FILTER (WHERE attributes->>'<candidate key>' IS NOT NULL) AS populated
FROM records
WHERE span_name = '<chosen span>'
LIMIT 1
```

**3. Read truncated samples to learn each value's shape.**

```sql
SELECT trace_id, span_id, substr(attributes->>'<key>', 1, 400) AS sample
FROM records
WHERE span_name = '<chosen span>'
ORDER BY start_timestamp DESC
LIMIT 3
```

**4. If the inputs and outputs live on different spans,** relate them through the trace tree:
`trace_id` groups a trace, and `parent_span_id` points to the parent's `span_id`.

```sql
-- the chosen span, plus a value from its parent
SELECT c.trace_id, c.span_id, p.span_name AS parent, c.attributes->>'<key>' AS value
FROM records c
JOIN records p ON p.span_id = c.parent_span_id AND p.trace_id = c.trace_id
WHERE c.span_name = '<chosen span>'
LIMIT 20
```

The same join also narrows the selection to spans that ran under a particular parent, by
filtering on `p.span_name`.

## Reading What Discovery Shows

- **The value isn't on any span.** The application didn't record it, so there is nothing to
  extract. Tell the user what would need to be recorded instead of approximating it.
- **Values are structured** (arrays, nested objects). Select the subtree with `->` and pick the
  part you need in Python. That is easier to get right than deep SQL paths, especially when
  the position of the element you want varies from row to row.
- **Values share boilerplate.** When every value starts with the same long preamble, a keyword
  filter on the whole value matches almost every row. Read a few samples, then filter on the
  part that varies, for example `right(<expr>, 1500)`.
- **One input appears several times.** The same input re-run produces several rows. Decide
  with the user whether each run is a case or whether to dedupe on the input expression.
- **Wording-based filters are approximate.** Before writing the extraction query, list the
  candidates with a short excerpt and check that the filter keeps what the user meant and
  drops what they didn't.

## Scrubbed Values

Logfire's scrubber replaces values that match sensitive patterns at ingest, leaving text like
`[Scrubbed due to '<pattern>']`. Ordinary prose that merely mentions a sensitive word can be
caught too. The original content cannot be recovered. Scrubbing can replace a whole value or
a single field nested inside a JSON value, so match the marker anywhere:
`<expr> LIKE '%[Scrubbed due to%'`. During discovery, count how many candidate rows have
scrubbed inputs or outputs, drop them when mapping (or keep partly scrubbed rows only if the
user agrees), and tell the user how many were lost. Fixing it for future traces means changing
the application's scrubbing options; that is the user's call.

## Choosing Rows

| Goal | Approach |
|------|----------|
| Successful behaviour | `NOT is_exception`, and the output value present (`IS NOT NULL`) |
| Failures | `is_exception` on the chosen span, or join to child spans in the same trace that errored |
| Coverage across inputs | Sample instead of taking the latest rows: `ORDER BY random()`, or one row per group with `row_number() OVER (PARTITION BY <expr> ORDER BY start_timestamp DESC) = 1` in a CTE |
| One environment | `deployment_environment = '<name>'` |
| Duplicate inputs | Keep one whole row per input: `row_number() OVER (PARTITION BY <input expr> ORDER BY start_timestamp DESC) = 1` in a CTE. Don't aggregate columns separately (`max(trace_id)`, `max(span_id)`), because that can pair ids and values from different runs |
