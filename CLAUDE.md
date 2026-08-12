**Pydantic Logfire** is an observability platform built on OpenTelemetry. This repository contains the Python SDK for Logfire and documentation. The server application for recording and displaying data is closed source.

Key aspects:
- Opinionated wrapper around OpenTelemetry (traces, metrics, logs)
- Extensive integrations with popular Python packages
- SQL-based querying of telemetry data

# Code Quality

Pre-commit automatically runs ruff and pyright, but you can also run `make format/lint/typecheck` to run them explicitly, particularly to check files that haven't been changed.

# Documentation

Docs are rendered and deployed through the `pydantic/unified-docs` pipeline. Do not use MkDocs checks in this repository.

When linking between pages in this repository, use source-relative `.md` links. Published routes can
differ from source paths because [`docs/navigation.yml`](docs/navigation.yml) defines the published
sidebar and route map. When adding, moving, or removing a public docs page, update that manifest in
the same PR. Its public schema provides editor validation; contributors do not need a unified-docs
checkout. Verify the page and any anchor in a rendered preview, and never include the
deployment-specific `/docs` prefix in source links.

## Writing standard

**The full documentation style guide is [`dev-docs/documentation-style-guide.md`](dev-docs/documentation-style-guide.md)** — page templates, the terminology glossary, the pre-publish checklist, the anti-pattern catalog, and the rules for AI-assisted authoring. Read it before writing or substantially editing a docs page.

Every page in the public docs (`docs/`) is held to one standard:

> If an expert in some other field who has just started building with AI tools wouldn't know what it means, we spell out the acronym, we explain the term in place, or we rewrite the sentence to be human friendly.

This is about _introducing_ terms, not avoiding them — give the real word plus a plain-language hand-hold at first use. Docstrings and other in-code text follow normal API-reference conventions and are out of scope.

# Core Structure

```
logfire/
├── __init__.py              # Public API via DEFAULT_LOGFIRE_INSTANCE
├── _internal/               # Internal implementation
│   ├── main.py              # Logfire and LogfireSpan classes
│   ├── config.py            # LogfireConfig, configuration setup
│   ├── config_params.py     # Environment variable and config file handling
│   ├── tracer.py            # ProxyTracerProvider, tracer wrapping
│   ├── metrics.py           # ProxyMeterProvider, metrics handling
│   ├── exporters/           # OTLP, console, test exporters and processors
│   ├── integrations/        # Framework-specific instrumentation
│   ├── auto_trace/          # AST rewriting for auto-instrumentation
│   └── ...
├── integrations/            # Public integration APIs
└── experimental/            # Experimental features

logfire-api/                 # No-op shim package for libraries
tests/                       # Test suite
docs/                        # Documentation source for unified docs
```

# Testing

Tests that create spans should follow this pattern:

```python
from inline_snapshot import snapshot
from logfire.testing import TestExporter
import logfire

def test_my_thing(exporter: TestExporter):
    # create spans, e.g:
    with logfire.span("a span"):
        ...

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot()
```

Then run `uv run pytest -k test_my_thing --inline-snapshot=fix` to automatically fill in `snapshot()` with a list of dicts and check that the results are sane.
If the output changes, running again will automatically update the snapshot in the code.
`TestExporter` normalizes common things. If some remaining fields are non-deterministic (e.g., IDs, timestamps), use `dirty_equals` matchers, e.g:

```python
from dirty_equals import IsStr
from inline_snapshot import snapshot

assert ... == snapshot({
    'name': 'foo',
    'random_id': IsStr(),
})
```

Use `@pytest.mark.anyio` for async tests.

Some tests are decorated with `@pytest.mark.vcr()` and use `pytest-recording` to record HTTP interactions. Existing VCR cassette files should suffice. When creating a new test like this, run `uv run pytest -k test_my_thing --inline-snapshot=fix --record-mode=rewrite`.

Tests should use user-facing APIs as much as possible. Minimize mocking and reaching into internals.

Avoid constructing `LogfireConfig` or `Logfire` instances unless absolutely necessary. Use `logfire.configure()` instead, typically with the `config_kwargs` fixture, and even then only if the default configuration done for each test doesn't already suffice.

There's no need to write `lf = logfire.configure(...); lf.foo()`. Write `logfire.configure(...); logfire.foo()`. There's also generally no need to explicitly call `logfire.shutdown()`.

# logfire-api

The `logfire-api` package is a no-op shim that libraries can depend on to avoid hard dependencies on Logfire itself. It provides minimal 'implementations' in `logfire-api/logfire_api/__init__.py`, which needs to be kept up to date with the public API of the `logfire` module, especially if `test_logfire_api.py` starts failing. The rest is just `.pyi` stubs which should be ignored and are autogenerated when needed during release.

# CI

CI is required to pass on main, so pre-existing CI failures are unlikely. If the same test fails across multiple Python version jobs, it's almost certainly caused by your changes — investigate rather than assuming it's a flaky pre-existing issue.

## Coverage

Coverage must be 100%. The bar is the `uv run coverage report --fail-under 100` step of the `coverage` job in [`.github/workflows/main.yml`](.github/workflows/main.yml), not `pyproject.toml` — `[tool.coverage.report]` sets no `fail_under`, so a plain local `coverage report` exits 0 on a regression. Run `make testcov`, then `uv run coverage report --fail-under 100`, before pushing. CI combines coverage across the whole test matrix, so a line reached only by another matrix job shows as missed locally; investigate a local miss before deleting or excluding the code.

## The check job

The `check` job only aggregates the other jobs with the `alls-green` action and produces no result of its own. When `check` fails, open the job it names and read that job's log.

## Pydantic version coverage

PR CI only tests pydantic latest plus one extra job at pydantic 2.4. The full set of supported minor versions (2.4, 2.5, 2.6, ... up through main) is exercised by the weekly job in `.github/workflows/weekly_deps_test.yml`, which is the contract: every minor version listed there is meant to keep working.

When something fails on pydantic 2.4, do not assume it is a 2.4-only quirk. The same problem is likely to affect some of 2.5–2.11 as well. Investigate which versions are actually affected (e.g. read the upstream changelog, install one of the in-between versions locally and reproduce) and fix or work around for the whole affected range. A green PR CI is not enough — if you only verify against 2.4 and latest, the weekly job will fail later even though the PR merged cleanly.

# Iterating on a pull request

A pull request is ready when CI is green and no review thread is unresolved. Run this loop until both hold.

1. Watch the checks until they settle, then fix every failure.
2. Read each new review comment. Several AI reviewers comment on pull requests here; verify each finding against this repository's code, configuration and history before acting on it. Do not assume a reviewer is right, and do not assume it is wrong.
3. Fix what the valid findings call for. Reply to every thread with what you changed, or with the evidence that the finding does not apply here.
4. Resolve each thread once you have replied. Leave a thread unresolved only to hold an open question that needs a maintainer's decision — one the repository's own docs, configuration and history cannot settle.
5. Return to step 1 after every push, because reviewers comment again on the new commit.

A reviewer can be right about Python in general and wrong about this repository. For example, a reviewer may report a Ruff `S106` violation (hardcoded password passed as an argument). `[tool.ruff.lint]` in `pyproject.toml` selects `E4`, `E7`, `E9` and `F`, plus an `extend-select` list that does not contain `S`, and `uv run ruff check --select S106` reports many pre-existing hits. The rule is not enabled, so there is nothing to fix. Check the configuration that governs a finding before you accept it.

# Misc

Use `git push origin HEAD` to push, not just `git push`, so that it pushes to the current branch without needing to set upstream explicitly.
