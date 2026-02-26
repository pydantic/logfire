<!-- braindump: rules extracted from PR review patterns -->

# tests/ Guidelines

## Testing

- Use VCR cassettes instead of mocking for HTTP requests in tests — Cassette-based recording captures real API interactions including headers, timing, and edge cases that mocks miss, making tests more realistic and maintainable
- Test real behavior, not state manipulation — assert outcomes from genuine code execution — Prevents false positives from tests that pass without validating actual functionality, and catches bugs that only surface through real execution paths
- Add explicit assertions in tests — implicit checks (e.g., "no exception raised") hide intent and make failures unclear — Explicit assertions document expected behavior and produce clearer failure messages when tests break
- Use `snapshot()` for assertions on variable values (counts, timestamps, IDs) — prevents brittle tests when non-deterministic data changes — Snapshot testing with `dirty_equals` matchers validates structure and types while tolerating expected variability, making tests resilient to sampling fluctuations and timing differences.
- Use `pytest.warns()` to assert expected warnings — makes tests explicit and verifies warnings occur — Prevents silent failures when expected warnings don't occur and makes test intent clear, but skip for environment-dependent warnings to avoid flakiness

<!-- /braindump -->