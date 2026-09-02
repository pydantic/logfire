# Snowflake integration design

## Overview

Add a `logfire.instrument_snowflake()` integration that instruments
`snowflake-connector-python`, giving each query a span with its SQL text,
Snowflake's own query ID, row count, and target warehouse/database/schema —
matching the coverage every other SQL database integration in this repo
already provides (Postgres via `psycopg`/`asyncpg`, `sqlite3`, `pymongo`,
etc.).

## Background

Snowflake telemetry splits into two lanes that need fundamentally different
delivery mechanisms:

1. **Real-time query telemetry** — the SQL a client sent, the query ID
   Snowflake assigned, how long it took, how many rows came back, whether it
   errored. This only exists at the moment a client issues the query; there's
   no way to reconstruct it later.
2. **Compute/resource usage** — credits consumed, bytes scanned, warehouse
   queuing, storage. This lives in Snowflake's own account-usage views and is
   only queryable well after the fact (`INFORMATION_SCHEMA.QUERY_HISTORY` is
   the freshest source, still on the order of a minute of lag).

Lane 2 is already solved by the OpenTelemetry Collector's `snowflakereceiver`
(part of `opentelemetry-collector-contrib`), which polls those views and
exports metrics via OTLP — that's collector configuration, not Python code,
and needs nothing from this repo.

Lane 1 has no existing tooling to build on. `snowflake-connector-python` has
no built-in OpenTelemetry support (open, unresolved upstream issue:
[snowflakedb/snowflake-connector-python#1891](https://github.com/snowflakedb/snowflake-connector-python/issues/1891)),
and there is no `opentelemetry-instrumentation-snowflake` package on PyPI.
This spec covers building lane 1 as a Logfire integration.

Because `snowflake-snowpark-python`'s `Session` executes all of its generated
SQL through the same `snowflake-connector-python` cursor under the hood,
instrumenting the connector layer gives Snowpark users span coverage too,
without any Snowpark-specific code. The span will show the SQL Snowpark
generated rather than the DataFrame method that triggered it — see
Non-goals.

## Non-goals (v1)

- **Compute/warehouse usage data.** Not fetched or surfaced by this
  integration. The query span carries Snowflake's `sfqid` (query ID) as an
  attribute so a user can manually correlate it, in Logfire's query view,
  with usage data arriving later via the Collector's `snowflakereceiver` —
  documented as a "see also," not built.
- **Snowpark DataFrame-level spans.** No parent span named after the
  triggering DataFrame action (`collect()`, `to_pandas()`, etc.). Noted as a
  natural phase-2 addition once this integration is stable.
- **`execute_async` / async query polling.** Snowflake's fire-and-poll async
  execution model doesn't fit the request/response span this design
  produces. Left as a known gap; `execute()`/`executemany()` (the common
  synchronous path) are in scope.

## Architecture

Follows the hand-rolled-patch pattern already used by
[`logfire/_internal/integrations/surrealdb.py`](../../../logfire/_internal/integrations/surrealdb.py)
rather than the wrap-an-existing-OTel-instrumentor pattern used by
`psycopg.py`/`sqlite3.py` — there is no upstream instrumentor to delegate to,
so this integration creates spans directly with `logfire_instance.span(...)`.

New/changed files:

| File | Change |
|---|---|
| `logfire/_internal/integrations/snowflake.py` | New. Instrumentation logic. |
| `logfire/_internal/main.py` | New `Logfire.instrument_snowflake()` method. |
| `logfire-api/logfire_api/__init__.py` | No-op shim stub for `instrument_snowflake`. |
| `tests/otel_integrations/test_snowflake.py` | New. |
| `docs/integrations/databases/snowflake.md` | New. |
| `docs/navigation.yml` | Add entry under `Databases`, alongside the existing `surrealdb.md` entry. |
| `pyproject.toml` | New `snowflake = ["snowflake-connector-python"]` extra; add `snowflake-connector-python` to the dev/test dependency group. |

## Public API

```python
def instrument_snowflake(
    self,
    conn_or_module: ModuleType | Literal['snowflake.connector'] | None | SnowflakeConnection = None,
) -> None:
    """Instrument the `snowflake-connector-python` client so that spans are
    automatically created for each query.

    Args:
        conn_or_module: Pass a single connection instance to instrument only
            that connection. Pass the `snowflake.connector` module (or leave
            as `None`) to instrument all connections, existing and future.
    """
```

Mirrors the existing `instrument_surrealdb`/`instrument_psycopg` signature
convention: no argument instruments everything available; a connection
instance narrows it to just that connection.

## Instrumented surface

- **`snowflake.connector.connect()`** → span `snowflake connect`.
  Attributes: `account`, `warehouse`, `database`, `schema`, `role` (all
  non-secret connection kwargs). `password`, `token`, and `private_key`
  (and equivalents) are explicitly dropped before span creation, as
  defense-in-depth on top of Logfire's scrubber — the same reasoning
  `surrealdb.py` applies to `token`.
- **`SnowflakeCursor.execute()` / `executemany()`** → span `snowflake
  execute`. Attributes:
  - SQL text and bind parameters, passed through Logfire's standard
    scrubber.
  - `sfqid` (Snowflake's query ID) and `rowcount`, read off the cursor once
    the call returns — this is the correlation key for lane 2.
  - `warehouse`, `database`, `schema` inherited from the parent connection,
    so a query is filterable without joining back to the connect span.
- Exceptions (`snowflake.connector.errors.*`) are left to propagate
  normally; Logfire's standard span-exception capture records them without
  any bespoke handling.

## Error handling

- Missing dependency: `instrument_snowflake()` raises `ImportError` with
  `pip install 'logfire[snowflake]'` install instructions, matching
  `sqlite3.py`'s pattern.
- Instrumentation-internal failures (e.g., an unexpected missing attribute
  on a cursor object) are wrapped in `handle_internal_errors` (as
  `surrealdb.py` does), so a defect in this module can never break a user's
  actual Snowflake call.
- Idempotency: wrapped methods are marked (e.g. `wrapped_method._logfire_patched
  = True`) so calling `instrument_snowflake()` twice, or instrumenting both
  the module and one of its connections, does not double-wrap. Covered by a
  test, mirroring `test_surrealdb.py`'s idempotency check.

## Testing

Unlike SurrealDB (ships an embedded, credential-free connection mode usable
in CI) or Postgres (runnable as a CI service container), Snowflake has no
local or dockerizable mode — every real connection needs live cloud
credentials. Test strategy:

- Primary suite (`tests/otel_integrations/test_snowflake.py`) mocks
  `snowflake.connector`'s connection/cursor objects to return canned
  `sfqid`/`rowcount`/rows, and asserts span shape via
  `exporter.exported_spans_as_dict(parse_json_attributes=True) ==
  snapshot(...)` per this repo's standard `TestExporter` pattern. Covers:
  span names and attributes for `connect`/`execute`/`executemany`,
  scrubbing of SQL text and bind params containing sensitive-looking
  values, presence of `sfqid`/`rowcount`, the exception path, and
  idempotency of double-instrumenting.
- No VCR cassette is needed — the test doubles are at the connector-object
  level, not the HTTP level.
- Must reach 100% coverage per this repo's CI bar
  (`uv run coverage report --fail-under 100`); no live-account integration
  test is in scope for v1 given there's no way to run one in this repo's CI
  without provisioning Snowflake credentials as a secret, which is a
  separate decision outside this spec.

## Documentation

`docs/integrations/databases/snowflake.md` follows the existing
`surrealdb.md` template (per this repo's
[documentation style guide](../../../dev-docs/documentation-style-guide.md)):
what gets captured, install instructions, a "why you'd want this" framing
for a reader new to Logfire, and a "See also" pointing at the
`snowflakereceiver` Collector setup for compute/usage telemetry (lane 2),
making the split between the two lanes explicit to readers rather than
implying this integration covers both. Add the corresponding entry to
`docs/navigation.yml` under the `Databases` section in the same PR.

## Open questions

- Exact attribute name for the query ID (`sfqid` vs a more descriptive key
  like `snowflake.query_id`) should follow whatever OTel semantic
  convention naming this repo already uses for other DB attributes —
  confirm during implementation by checking how `psycopg.py`/`sqlite3.py`
  name their `db.*` attributes.
- Whether a live-account integration test (gated behind CI secrets, skipped
  by default) is worth adding later is left to a maintainer's judgment, not
  decided here.
