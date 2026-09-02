# Snowflake Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `logfire.instrument_snowflake()`, which patches `snowflake-connector-python` so that every query gets a span with its SQL, Snowflake's query ID (`sfqid`), row count, and target warehouse/database/schema.

**Architecture:** Hand-rolled monkeypatching of `snowflake.connector.connect` and `SnowflakeCursor.execute`/`executemany`, following the same pattern `logfire/_internal/integrations/surrealdb.py` uses (there is no upstream `opentelemetry-instrumentation-snowflake` package to delegate to). Patching happens at the real, installed `snowflake.connector` classes — no shim classes ship in this repo.

**Tech Stack:** Python, `snowflake-connector-python` (dev/test dependency only — this integration adds no separate OTel-instrumentor package), `logfire` core span API, `pytest` + `inline-snapshot` + `TestExporter`.

**Spec:** `docs/superpowers/specs/2026-09-02-snowflake-integration-design.md`

## Global Constraints

- Compute/warehouse usage telemetry (credits, bytes scanned, etc.) is **out of scope**. Do not add any code that queries `ACCOUNT_USAGE`/`QUERY_HISTORY`. Document it only as a "see also" pointing at the OTel Collector's `snowflakereceiver`.
- No Snowpark-specific (`snowflake.snowpark`) code. Only `snowflake-connector-python` is instrumented.
- `execute_async` is out of scope — do not instrument it.
- 100% coverage is required (`uv run coverage report --fail-under 100`), per this repo's CI bar.
- Tests must not perform real network I/O against Snowflake — there is no local/dockerizable Snowflake, and no live-account credentials are available in this repo's CI.
- Never let a credential-like connection kwarg (`password`, `token`, `token_file_path`, `master_token`, `session_token`, `passcode`, `private_key`, `private_key_file`, `private_key_passphrase`, `private_key_file_pwd`, `oauth_client_secret`) reach a span attribute. Read connection context from `SnowflakeConnection`'s public read-only properties (`account`, `warehouse`, `database`, `schema`, `role`) rather than from the kwargs passed to `connect()` — this avoids the whole class of risk instead of denylisting kwargs.
- Every new `instrument_*` public method needs a matching no-op stub in `logfire-api/logfire_api/__init__.py` (see `CLAUDE.md`).

---

### Task 1: Module skeleton, dev dependency, and `connect()` instrumentation

**Files:**
- Create: `logfire/_internal/integrations/snowflake.py`
- Modify: `logfire/_internal/main.py` (add `Logfire.instrument_snowflake` near `instrument_surrealdb`, ~line 999)
- Modify: `logfire-api/logfire_api/__init__.py` (add a no-op stub, alongside `instrument_surrealdb`, ~line 173 and ~line 253)
- Modify: `pyproject.toml` (add `"snowflake-connector-python >= 3"` to the `dev` group in `[dependency-groups]`, alongside the existing `"surrealdb >= 0"` line ~216 — no `[project.optional-dependencies]` extra is needed, matching how `surrealdb` itself has none)
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- Produces: `instrument_snowflake(logfire_instance: Logfire, conn_or_module: ModuleType | SnowflakeConnection | None) -> None` in `logfire/_internal/integrations/snowflake.py`.
- Produces: `Logfire.instrument_snowflake(self, conn_or_module: ModuleType | SnowflakeConnection | None = None) -> None` in `logfire/_internal/main.py`, the public entrypoint later tasks' tests will call as `logfire.instrument_snowflake()`.

- [ ] **Step 1: Add the dev dependency**

Edit `pyproject.toml`, in the `dev = [...]` group (`[dependency-groups]`, the same list containing `"surrealdb >= 0"` around line 216), add:

```toml
    "snowflake-connector-python >= 3",
```

Run: `uv sync`
Expected: `snowflake-connector-python` installs without touching `[project.optional-dependencies]`.

- [ ] **Step 2: Write the failing test for `connect()` instrumentation**

Create `tests/otel_integrations/test_snowflake.py`:

```python
from __future__ import annotations

from typing import Any

import pytest
from inline_snapshot import snapshot
from snowflake.connector import connection as sf_connection

import logfire
from logfire._internal.exporters.test import TestExporter


class FakeConnection:
    def __init__(self, **kwargs: Any) -> None:
        self.account = kwargs.get('account')
        self.warehouse = kwargs.get('warehouse')
        self.database = kwargs.get('database')
        self.schema = kwargs.get('schema')
        self.role = kwargs.get('role')


@pytest.fixture(autouse=True)
def fake_snowflake_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(**kwargs: Any) -> FakeConnection:
        return FakeConnection(**kwargs)

    monkeypatch.setattr('snowflake.connector.connect', fake_connect)


def test_instrument_connect(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    import snowflake.connector

    conn = snowflake.connector.connect(
        account='my_account',
        warehouse='my_wh',
        database='my_db',
        schema='my_schema',
        role='my_role',
        password='super-secret',
    )
    assert conn.account == 'my_account'

    assert exporter.exported_spans_as_dict() == snapshot()
```

- [ ] **Step 2b: Run test to verify it fails**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_connect -v`
Expected: FAIL — `AttributeError: module 'logfire' has no attribute 'instrument_snowflake'` (or `ModuleNotFoundError` if `snowflake` isn't importable yet — resolve step 1 first).

- [ ] **Step 3: Implement `instrument_snowflake` for the `connect()` path**

Create `logfire/_internal/integrations/snowflake.py`:

```python
from __future__ import annotations

import functools
from types import ModuleType
from typing import Any

import snowflake.connector as sf_connector
from snowflake.connector.connection import SnowflakeConnection
from snowflake.connector.cursor import SnowflakeCursor

from logfire import Logfire
from logfire._internal.utils import handle_internal_errors

CONNECTION_ATTRS = ('account', 'warehouse', 'database', 'schema', 'role')


def _connection_attributes(conn: Any) -> dict[str, Any]:
    return {name: getattr(conn, name, None) for name in CONNECTION_ATTRS}


def instrument_snowflake(
    logfire_instance: Logfire,
    conn_or_module: ModuleType | SnowflakeConnection | None,
) -> None:
    if conn_or_module is None or conn_or_module is sf_connector:
        _instrument_module(logfire_instance)
    elif isinstance(conn_or_module, SnowflakeConnection):
        _instrument_connection(logfire_instance, conn_or_module)
    else:
        raise ValueError(f"Don't know how to instrument {conn_or_module!r}")


def _instrument_module(logfire_instance: Logfire) -> None:
    original_connect = sf_connector.connect
    if getattr(original_connect, '_logfire_patched', False):
        return

    @functools.wraps(original_connect)
    def wrapped_connect(**kwargs: Any) -> SnowflakeConnection:
        with logfire_instance.span('snowflake connect', _span_name='snowflake connect') as span:
            conn = original_connect(**kwargs)
            with handle_internal_errors:
                for key, value in _connection_attributes(conn).items():
                    span.set_attribute(key, value)
            return conn

    wrapped_connect._logfire_patched = True  # type: ignore[attr-defined]
    sf_connector.connect = wrapped_connect
```

- [ ] **Step 4: Wire the public API method**

In `logfire/_internal/main.py`, add just after `instrument_surrealdb` (~line 1013):

```python
    def instrument_snowflake(
        self, conn_or_module: ModuleType | SnowflakeConnection | None = None
    ) -> None:
        """Instrument the [Snowflake Connector for Python](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector)
        so that a span is created for each query.

        Args:
            conn_or_module: Pass a single connection instance to instrument only that connection.
                By default (`None`), all connections are instrumented, including ones created later.
        """
        from .integrations.snowflake import instrument_snowflake

        self._warn_if_not_initialized_for_instrumentation()
        instrument_snowflake(self, conn_or_module)
```

In the `if TYPE_CHECKING:` block near the top of `main.py` (starts at line 72), add, next to the existing surrealdb imports at lines 99–100:

```python
    from snowflake.connector.connection import SnowflakeConnection
```

- [ ] **Step 5: Add the `logfire-api` no-op stub**

In `logfire-api/logfire_api/__init__.py`, add next to `instrument_surrealdb` (~line 173):

```python
            def instrument_snowflake(self, *args, **kwargs) -> None: ...
```

And next to the `instrument_surrealdb = DEFAULT_LOGFIRE_INSTANCE.instrument_surrealdb` line (~line 253):

```python skip-run="true" skip-reason="code-fragment"
        instrument_snowflake = DEFAULT_LOGFIRE_INSTANCE.instrument_snowflake
```

- [ ] **Step 6: Run test to verify it passes, then fill in the snapshot**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_connect -v --inline-snapshot=fix`
Expected: PASS, with the snapshot filled in showing one span named `snowflake connect` with attributes `account='my_account'`, `warehouse='my_wh'`, `database='my_db'`, `schema='my_schema'`, `role='my_role'`, and **no** `password` attribute anywhere.

- [ ] **Step 7: Commit**

```bash
git add logfire/_internal/integrations/snowflake.py logfire/_internal/main.py logfire-api/logfire_api/__init__.py pyproject.toml tests/otel_integrations/test_snowflake.py uv.lock
git commit -m "feat(snowflake): instrument connect()"
```

---

### Task 2: Instrument `SnowflakeCursor.execute`/`executemany` (global default)

**Files:**
- Modify: `logfire/_internal/integrations/snowflake.py`
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- Consumes: `_connection_attributes(conn) -> dict[str, Any]` from Task 1.
- Produces: `_patch_cursor_class(logfire_instance: Logfire) -> None`, called from `_instrument_module`. After this task, every `SnowflakeCursor.execute`/`executemany` call — from a connection instrumented via `instrument_snowflake()` with no argument — produces a span.

- [ ] **Step 1: Write the failing test**

Add to `tests/otel_integrations/test_snowflake.py`, using a `FakeConnection` whose `cursor()` builds a real `SnowflakeCursor` (its `__init__` only stores the connection reference — no network I/O — so this is safe) and monkeypatching `SnowflakeCursor.execute`/`executemany` to canned results instead of hitting the network:

```python skip-run="true" skip-reason="code-fragment"
from snowflake.connector.cursor import SnowflakeCursor


class FakeConnection:
    def __init__(self, **kwargs: Any) -> None:
        self.account = kwargs.get('account')
        self.warehouse = kwargs.get('warehouse')
        self.database = kwargs.get('database')
        self.schema = kwargs.get('schema')
        self.role = kwargs.get('role')

    def cursor(self) -> SnowflakeCursor:
        return SnowflakeCursor(self)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def fake_snowflake_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any):
        self._sfqid = 'fake-sfqid-1'
        self._total_rowcount = 3
        return self

    def fake_executemany(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any):
        self._sfqid = 'fake-sfqid-2'
        self._total_rowcount = len(seqparams)
        return self

    monkeypatch.setattr(SnowflakeCursor, 'execute', fake_execute)
    monkeypatch.setattr(SnowflakeCursor, 'executemany', fake_executemany)


def test_instrument_execute(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role')
    cursor = conn.cursor()
    cursor.execute('select * from my_table where id = %s', (1,))

    assert exporter.exported_spans_as_dict() == snapshot()


def test_instrument_executemany(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role')
    cursor = conn.cursor()
    cursor.executemany('insert into my_table values (%s)', [(1,), (2,), (3,)])

    assert exporter.exported_spans_as_dict() == snapshot()
```

Note: `fake_snowflake_execute` must monkeypatch `SnowflakeCursor.execute`/`executemany` to the fakes **before** `logfire.instrument_snowflake()` runs in the test body, so that our patch wraps the fake (network-free) implementation rather than the real one. Since both fixtures are `autouse`, and pytest runs fixtures before the test body, this ordering holds as long as this fixture doesn't itself call `instrument_snowflake()`.

- [ ] **Step 1b: Run tests to verify they fail**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py -k "execute" -v`
Expected: FAIL — only the `snowflake connect` behavior exists so far; no span is produced for `cursor.execute()`/`executemany()`.

- [ ] **Step 2: Implement cursor patching**

Extend `logfire/_internal/integrations/snowflake.py`:

```python
def _instrument_module(logfire_instance: Logfire) -> None:
    # The connect-patch guard and the cursor-patch guard are independent: even when connect()
    # is already patched, _patch_cursor_class still runs and makes its own idempotency check,
    # so re-instrumenting after something else resets SnowflakeCursor.execute (Task 5) still works.
    original_connect = sf_connector.connect
    if not getattr(original_connect, '_logfire_patched', False):

        @functools.wraps(original_connect)
        def wrapped_connect(**kwargs: Any) -> SnowflakeConnection:
            with logfire_instance.span('snowflake connect', _span_name='snowflake connect') as span:
                conn = original_connect(**kwargs)
                with handle_internal_errors:
                    for key, value in _connection_attributes(conn).items():
                        span.set_attribute(key, value)
                return conn

        wrapped_connect._logfire_patched = True  # type: ignore[attr-defined]
        sf_connector.connect = wrapped_connect

    _patch_cursor_class(logfire_instance)


def _patch_cursor_class(logfire_instance: Logfire) -> None:
    original_execute = SnowflakeCursor.__dict__.get('execute', SnowflakeCursor.execute)
    if not getattr(original_execute, '_logfire_patched', False):
        SnowflakeCursor.execute = _wrap_execute(logfire_instance, original_execute)  # type: ignore[method-assign]

    original_executemany = SnowflakeCursor.__dict__.get('executemany', SnowflakeCursor.executemany)
    if not getattr(original_executemany, '_logfire_patched', False):
        SnowflakeCursor.executemany = _wrap_executemany(logfire_instance, original_executemany)  # type: ignore[method-assign]


def _wrap_execute(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        attributes: dict[str, Any] = {'command': command, 'params': params}
        with handle_internal_errors:
            attributes.update(_connection_attributes(self.connection))
        with logfire_instance.span('snowflake execute {command}', _span_name='snowflake execute', **attributes) as span:
            result = original(self, command, params, *args, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped


def _wrap_executemany(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any) -> Any:
        attributes: dict[str, Any] = {'command': command, 'seqparams': seqparams}
        with handle_internal_errors:
            attributes.update(_connection_attributes(self.connection))
        with logfire_instance.span('snowflake executemany {command}', _span_name='snowflake executemany', **attributes) as span:
            result = original(self, command, seqparams, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped
```

- [ ] **Step 3: Run tests to verify they pass, then fill in snapshots**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py -k "execute" -v --inline-snapshot=fix`
Expected: PASS. `test_instrument_execute`'s snapshot shows a `snowflake execute` span with `command`, `params=[1]`, `account`/`warehouse`/`database`/`schema`/`role`, `sfqid='fake-sfqid-1'`, `rowcount=3`. `test_instrument_executemany`'s snapshot shows a `snowflake executemany` span with `seqparams`, the same connection attributes, `sfqid='fake-sfqid-2'`, `rowcount=3`.

- [ ] **Step 4: Commit**

```bash
git add logfire/_internal/integrations/snowflake.py tests/otel_integrations/test_snowflake.py
git commit -m "feat(snowflake): instrument cursor execute/executemany"
```

---

### Task 3: Narrow instrumentation to a single connection instance

**Files:**
- Modify: `logfire/_internal/integrations/snowflake.py`
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- Consumes: `_wrap_execute`, `_wrap_executemany` from Task 2 (both take `(logfire_instance, original)` and return an unbound callable usable via `types.MethodType`).
- Produces: `_instrument_connection(logfire_instance: Logfire, conn: SnowflakeConnection) -> None`, reachable via `instrument_snowflake(logfire_instance, conn)` per the `isinstance(conn_or_module, SnowflakeConnection)` branch already routed in Task 1.

- [ ] **Step 1: Write the failing test**

`instrument_snowflake`'s single-connection branch checks `isinstance(conn_or_module, SnowflakeConnection)` (Task 1), so the test double for this task must be a real `SnowflakeConnection` subclass, not the plain `FakeConnection` used in Tasks 1–2. Add to `tests/otel_integrations/test_snowflake.py` (reusing the `fake_snowflake_execute` fixture from Task 2, but *not* the module-wide `fake_snowflake_connect` autouse fixture — this test instruments a connection object directly, so `snowflake.connector.connect` is never called):

```python skip-run="true" skip-reason="code-fragment"
class FakeSnowflakeConnection(SnowflakeConnection):
    def __init__(self, **kwargs: Any) -> None:
        # Deliberately skip SnowflakeConnection.__init__, which opens a real network
        # connection. Set only the private attributes its account/warehouse/database/
        # schema/role properties read (confirmed to be plain `self._account`-style reads).
        self._account = kwargs.get('account')
        self._warehouse = kwargs.get('warehouse')
        self._database = kwargs.get('database')
        self._schema = kwargs.get('schema')
        self._role = kwargs.get('role')

    def cursor(self, cursor_class: type = SnowflakeCursor) -> SnowflakeCursor:
        # Override rather than inherit: the real cursor() checks internal connection
        # state that __init__ never set up here.
        return cursor_class(self)


def test_instrument_single_connection(exporter: TestExporter) -> None:
    conn = FakeSnowflakeConnection(account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role')
    logfire.instrument_snowflake(conn)

    cursor = conn.cursor()
    cursor.execute('select 1')

    # A second, uninstrumented connection must not produce spans.
    other_conn = FakeSnowflakeConnection(account='other_account')
    other_conn.cursor().execute('select 2')

    assert exporter.exported_spans_as_dict() == snapshot()
```

- [ ] **Step 1b: Run test to verify it fails**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_single_connection -v`
Expected: FAIL — `NameError: name '_instrument_connection' is not defined`. Task 1's `instrument_snowflake` body already has the `elif isinstance(conn_or_module, SnowflakeConnection): _instrument_connection(logfire_instance, conn_or_module)` branch, but that name is only resolved when the line actually executes — which never happened in Tasks 1–2's tests (both call `instrument_snowflake()` with no argument) until this test calls it with a real connection instance.

- [ ] **Step 2: Implement connection-instance instrumentation**

Add `import types` to the top of `logfire/_internal/integrations/snowflake.py`, alongside the existing `import functools`. Then extend the file:

```python
def _instrument_connection(logfire_instance: Logfire, conn: SnowflakeConnection) -> None:
    original_cursor_factory = conn.cursor
    if getattr(original_cursor_factory, '_logfire_patched', False):
        return

    def wrapped_cursor_factory(*args: Any, **kwargs: Any) -> SnowflakeCursor:
        cursor = original_cursor_factory(*args, **kwargs)
        cursor.execute = types.MethodType(_wrap_execute(logfire_instance, SnowflakeCursor.execute), cursor)
        cursor.executemany = types.MethodType(_wrap_executemany(logfire_instance, SnowflakeCursor.executemany), cursor)
        return cursor

    wrapped_cursor_factory._logfire_patched = True  # type: ignore[attr-defined]
    conn.cursor = wrapped_cursor_factory  # type: ignore[method-assign]
```

- [ ] **Step 3: Run test to verify it passes, then fill in the snapshot**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_single_connection -v --inline-snapshot=fix`
Expected: PASS, with exactly one `snowflake execute` span (from `conn`, `sfqid='fake-sfqid-1'`) and none from `other_conn`.

- [ ] **Step 4: Commit**

```bash
git add logfire/_internal/integrations/snowflake.py tests/otel_integrations/test_snowflake.py
git commit -m "feat(snowflake): support instrumenting a single connection"
```

---

### Task 4: Idempotency

**Files:**
- Modify: `logfire/_internal/integrations/snowflake.py` (verify existing guards; add any missing)
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- Consumes: the `_logfire_patched` marker convention already applied to `wrapped_connect`, `SnowflakeCursor.execute`/`executemany`, and `wrapped_cursor_factory` in Tasks 1–3.

- [ ] **Step 1: Write the failing/characterizing test**

```python
def test_instrument_snowflake_idempotent(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()
    logfire.instrument_snowflake()  # should not double-wrap

    import snowflake.connector

    conn = snowflake.connector.connect(account='my_account')
    cursor = conn.cursor()
    cursor.execute('select 1')

    # Exactly one `snowflake connect` span and one `snowflake execute` span — not two of each.
    names = [s['name'] for s in exporter.exported_spans_as_dict()]
    assert names.count('snowflake connect') == 1
    assert names.count('snowflake execute') == 1
```

- [ ] **Step 1b: Run test**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_snowflake_idempotent -v`
Expected: this should already PASS given the `_logfire_patched` guards added in Tasks 1–2 (`getattr(original_connect, '_logfire_patched', False)` in `_instrument_module`, and the `SnowflakeCursor.__dict__.get(...)` + `_logfire_patched` check in `_patch_cursor_class`). If it fails, the guard is missing or checking the wrong object — fix `_instrument_module`/`_patch_cursor_class` so the second `instrument_snowflake()` call is a no-op for both connect and cursor patching, then re-run.

- [ ] **Step 2: Commit**

```bash
git add tests/otel_integrations/test_snowflake.py
git commit -m "test(snowflake): cover idempotent instrumentation"
```

---

### Task 5: Exception handling and internal-error safety net

**Files:**
- Modify: `logfire/_internal/integrations/snowflake.py` (no production changes expected — this task verifies existing `handle_internal_errors` usage and span-exception behavior with tests)
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- Consumes: `logfire_instance.span(...)`'s built-in exception recording (any exception raised inside the `with` block is captured on the span and re-raised — this is default `Logfire.span` behavior, not something this integration implements).

- [ ] **Step 1: Write the failing test for a failing query**

```python
class SnowflakeQueryError(Exception):
    pass


def test_instrument_execute_error(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account')
    cursor = conn.cursor()

    def broken_execute(self: SnowflakeCursor, command: str, params: Any = None, *a: Any, **k: Any):
        raise SnowflakeQueryError('syntax error')

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(SnowflakeCursor, 'execute', broken_execute)
        # Re-instrument so our wrapper picks up broken_execute as the new "original" to wrap.
        logfire.instrument_snowflake()
        with pytest.raises(SnowflakeQueryError):
            cursor.execute('select * from does_not_exist')

    spans = exporter.exported_spans_as_dict()
    assert spans[-1]['attributes']['logfire.level_num'] == 17  # error level
    assert 'exception' not in spans[-1] or spans[-1].get('events')
```

Note: because `_patch_cursor_class`'s idempotency guard (Task 4) checks `SnowflakeCursor.__dict__.get('execute')._logfire_patched`, and `mp.setattr` replaces `execute` with a *fresh*, unpatched `broken_execute`, calling `logfire.instrument_snowflake()` again inside the `with pytest.MonkeyPatch.context()` block re-wraps it — this is intentional and exercises the same idempotency-guard code path from Task 4 rather than fighting it.

- [ ] **Step 1b: Run test, adjust assertions to match actual span shape**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_execute_error -v --inline-snapshot=fix`
Replace the two manual `assert` lines above with a single `assert exporter.exported_spans_as_dict() == snapshot()` and let `--inline-snapshot=fix` capture the real shape (span status `error`, `logfire.level_num`, and an `events` entry describing the raised `SnowflakeQueryError`) — this repo's convention (see `test_surrealdb.py`, `test_psycopg.py`) is to assert the full snapshot rather than hand-picked keys.
Expected: PASS after the snapshot is filled in, confirming the exception propagates to the caller (`pytest.raises` catches it) *and* is recorded on the span — both for free from `logfire_instance.span(...)`, no bespoke error-handling code needed in this integration.

- [ ] **Step 2: Write the test for an internal instrumentation bug not breaking the user's call**

```python
def test_internal_error_does_not_break_query(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account')
    cursor = conn.cursor()

    # Simulate a bug in our own attribute-reading code: `connection` raises instead of
    # returning the real connection.
    monkeypatch.setattr(
        SnowflakeCursor, 'connection', property(lambda self: (_ for _ in ()).throw(RuntimeError('boom')))
    )

    result = cursor.execute('select 1')  # must not raise, despite the broken `connection` property
    assert result is cursor
```

- [ ] **Step 2b: Run test to verify it passes**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_internal_error_does_not_break_query -v`
Expected: PASS without any production code change — the `with handle_internal_errors:` block already wrapping `attributes.update(_connection_attributes(self.connection))` in `_wrap_execute` (Task 2) swallows and logs the `RuntimeError` instead of propagating it, so `original(self, command, params, *args, **kwargs)` still runs and returns normally. If this fails, `_connection_attributes(self.connection)` in `_wrap_execute`/`_wrap_executemany` is not actually inside a `handle_internal_errors` block — fix that first.

- [ ] **Step 3: Commit**

```bash
git add tests/otel_integrations/test_snowflake.py
git commit -m "test(snowflake): cover exception propagation and internal-error safety"
```

---

### Task 6: Missing-dependency `ImportError`

**Files:**
- Modify: `logfire/_internal/integrations/snowflake.py`
- Test: `tests/otel_integrations/test_snowflake.py`

**Interfaces:**
- No new public interfaces — this task only changes what happens on import failure.

**Background:** `Logfire.instrument_snowflake` (Task 1) does `from .integrations.snowflake import instrument_snowflake` *inside* the method body, exactly like `instrument_surrealdb` does — so `logfire/_internal/integrations/snowflake.py` is only ever imported the first time a caller actually calls `logfire.instrument_snowflake()`. That means a plain module-level `import snowflake.connector as sf_connector` at the top of that file (as written in Task 1) is already lazy from the caller's point of view — it just doesn't yet produce a friendly error message. This task only needs to wrap that existing import in a `try`/`except`, matching `logfire/_internal/integrations/sqlite3.py`'s pattern.

- [ ] **Step 1: Write the failing test**

`sys.modules[name] = None` is the standard way to force Python's import system to raise `ImportError` for a specific module without needing to fake `builtins.__import__`. Add:

```python
def test_instrument_snowflake_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.delitem(sys.modules, 'logfire._internal.integrations.snowflake', raising=False)
    monkeypatch.setitem(sys.modules, 'snowflake.connector', None)  # type: ignore[arg-type]

    with pytest.raises(ImportError, match=r'pip install snowflake-connector-python'):
        logfire.instrument_snowflake()
```

- [ ] **Step 1b: Run test to verify it fails**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py::test_instrument_snowflake_missing_dependency -v`
Expected: FAIL — the current unguarded `import snowflake.connector as sf_connector` in `logfire/_internal/integrations/snowflake.py` lets the raw `ImportError` (no `pip install` message) propagate instead of our custom one.

- [ ] **Step 2: Guard the existing import**

In `logfire/_internal/integrations/snowflake.py`, change:

```python
import snowflake.connector as sf_connector
from snowflake.connector.connection import SnowflakeConnection
from snowflake.connector.cursor import SnowflakeCursor
```

to:

```python
try:
    import snowflake.connector as sf_connector
    from snowflake.connector.connection import SnowflakeConnection
    from snowflake.connector.cursor import SnowflakeCursor
except ImportError as e:
    raise ImportError(
        'Run `pip install snowflake-connector-python` to use `logfire.instrument_snowflake()`.'
    ) from e
```

- [ ] **Step 3: Run all snowflake tests to verify nothing regressed, then the new test passes**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py -v`
Expected: all PASS, including `test_instrument_snowflake_missing_dependency`. The other tests in the file are unaffected because `sys.modules['snowflake.connector']` is only set to `None` for the duration of that one test (via `monkeypatch`, auto-reverted after).

- [ ] **Step 4: Commit**

```bash
git add logfire/_internal/integrations/snowflake.py tests/otel_integrations/test_snowflake.py
git commit -m "fix(snowflake): raise a clear ImportError when snowflake-connector-python is missing"
```

---

### Task 7: Documentation page and navigation entry

**Files:**
- Create: `docs/integrations/databases/snowflake.md`
- Modify: `docs/navigation.yml` (add entry under the `Databases` section, alongside the existing `surrealdb.md` entry ~line 385)

**Interfaces:** None — documentation only.

- [ ] **Step 1: Write the docs page**

Create `docs/integrations/databases/snowflake.md`, following the structure of `docs/integrations/databases/surrealdb.md` and this repo's [documentation style guide](../../dev-docs/documentation-style-guide.md) (spell out or explain any term a newcomer to observability tooling wouldn't know):

```markdown
---
title: "See Snowflake queries in Logfire"
description: "Add Logfire to the Snowflake Python client and see queries alongside the code that triggered them."
integration: logfire
---
# Snowflake

See the queries your app sends to [Snowflake][snowflake] alongside the code that triggered them.
Logfire records each query as a **span** (one unit of work: a single operation, with a name, a
start, and a duration). Related spans appear in the same **trace** (the full journey of one
request, made of nested spans), so you can find slow and failed queries in context.

**Instrumenting** Snowflake means adding the Logfire integration so it can see what your database
code is doing. The integration wraps the [Snowflake Connector for Python][snowflake-connector],
the client library that `snowflake-snowpark-python` and most other Snowflake tools also run their
queries through, so queries issued via Snowpark's `DataFrame` API get spans too.

## What you'll capture

- Each call to `connect()` as a span, with the target account, warehouse, database, schema, and
  role — connection secrets (password, token, private key, etc.) are never captured
- Each call to `execute()`/`executemany()` as a span, with the SQL text, bind parameters, row
  count, and Snowflake's own query ID (`sfqid`), with Logfire's standard **scrubbing**
  (automatically finding and hiding sensitive values in your telemetry, on your machine, before
  anything is sent) applied

## What this integration does not capture

Snowflake's **compute cost** for a query — credits consumed, bytes scanned, warehouse queuing —
isn't available at query time; Snowflake only exposes it minutes later through account-usage
views. To bring that data into Logfire, run the OpenTelemetry Collector's [`snowflakereceiver`][snowflakereceiver],
and use the `sfqid` attribute this integration records to match a query span to its later cost
data.

{{ before_you_start() }}

## Install Logfire and the Snowflake connector

Install `logfire`:

{{ install_logfire() }}

Install the separately distributed `snowflake-connector-python` package:

```bash
pip install snowflake-connector-python
```

## Record every query

Call [`logfire.instrument_snowflake()`][logfire.Logfire.instrument_snowflake] before connecting.
With no arguments, it records queries from every connection in the process, including ones made
later.

```python title="main.py" hl_lines="5"
import snowflake.connector

import logfire

logfire.configure()
logfire.instrument_snowflake()

conn = snowflake.connector.connect(
    account='<account>',
    user='<user>',
    password='<password>',
    warehouse='<warehouse>',
    database='<database>',
    schema='<schema>',
)
cursor = conn.cursor()
cursor.execute('select current_version()')
```

Run it with `python main.py`.

## Verify it worked

Open the [Live view](../../guides/web-ui/live.md). Within a few seconds, you should see spans
named `snowflake connect` and `snowflake execute`. Click a span to see its duration and
attributes, including `sfqid` and `rowcount`.

## Record one connection

Pass a connection instance to record queries from only that connection. Call
`logfire.instrument_snowflake(conn)` after connecting:

```python
import snowflake.connector

import logfire

logfire.configure()

conn = snowflake.connector.connect(account='<account>', user='<user>', password='<password>')
logfire.instrument_snowflake(conn)

cursor = conn.cursor()
cursor.execute('select current_version()')
```

## Troubleshoot missing spans

- **Importing `snowflake.connector` fails:** install the client separately with
  `pip install snowflake-connector-python`.
- **No spans appear:** call `logfire.configure()` before `logfire.instrument_snowflake()`, and
  instrument before connecting.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../../index.md).

[snowflake]: https://www.snowflake.com/
[snowflake-connector]: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector
[snowflakereceiver]: https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/snowflakereceiver/documentation.md
```

- [ ] **Step 2: Add the navigation entry**

In `docs/navigation.yml`, find the `Databases` section (containing the `surrealdb.md` entry around line 385) and add, in alphabetical order:

```yaml
          - title: "Snowflake"
            path: "integrations/databases/snowflake.md"
            slug: "integrations/databases/snowflake"
```

- [ ] **Step 3: Commit**

```bash
git add docs/integrations/databases/snowflake.md docs/navigation.yml
git commit -m "docs(snowflake): add integration page"
```

---

### Task 8: Full verification pass

**Files:** None (verification only).

**Interfaces:** None.

- [ ] **Step 1: Run the full test file**

Run: `uv run pytest tests/otel_integrations/test_snowflake.py -v`
Expected: all tests PASS.

- [ ] **Step 2: Run format, lint, and typecheck**

Run: `make format`
Run: `make lint`
Run: `make typecheck`
Expected: all clean. Fix any reported issues in `logfire/_internal/integrations/snowflake.py`, `logfire/_internal/main.py`, `logfire-api/logfire_api/__init__.py`, or the test file, then re-run.

- [ ] **Step 3: Check coverage on the new file**

Run: `uv run coverage run -m pytest tests/otel_integrations/test_snowflake.py`
Run: `uv run coverage report --include='*/integrations/snowflake.py'`
Expected: 100% on `logfire/_internal/integrations/snowflake.py`. Note per `CLAUDE.md`: this local number is a spot-check only — the authoritative 100% bar is CI's combined `coverage` job (`uv run coverage report --fail-under 100`), which runs after push, not something to try to fully reproduce locally.

- [ ] **Step 4: Run the `logfire-api` shim test**

Run: `uv run pytest -k test_logfire_api -v`
Expected: PASS, confirming the `instrument_snowflake` stub added in Task 1 matches the real method's presence.

- [ ] **Step 5: Commit any fixes from this task**

```bash
git add -u
git commit -m "chore(snowflake): fix lint/typecheck/coverage findings"
```

(Skip this commit if step 2–4 found nothing to fix.)
