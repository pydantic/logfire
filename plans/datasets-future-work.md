# Datasets SDK — Future Work

Deferred items from the initial datasets SDK implementation (PR #1711).

## Higher-Level Typed API

Instead of working with raw dicts returned by the API, provide a typed `DatasetHandle` that wraps the client and dataset identity:

```python
dataset = client.dataset('name', input_type=MyInput, output_type=MyOutput)
dataset.add_cases([Case(...)])
cases = dataset.list_cases()
```

This would require both sync and async variants (`DatasetHandle` / `AsyncDatasetHandle`).

## Upsert Behavior

Make `add_cases` idempotent by updating cases that already have a matching name in the dataset instead of creating duplicates.

Requirements:
- Backend: upsert endpoint + unique constraint on `(dataset_id, name)`
- SDK: optional confirmation prompt for overwrites, or a `on_conflict='update'|'skip'|'error'` parameter

## VCR Tests

Migrate from `httpx.MockTransport` to `pytest-recording` (VCR cassettes) for more realistic integration tests. This is the pattern used elsewhere in the logfire SDK.

## Backend / UI Issues

- **Schema validation on save**: The UI allows saving cases that don't match the dataset's JSON schema — validation should happen server-side.
- **Deleted cases not disappearing**: Occasionally deleted cases remain visible in the UI until a page refresh.
- **Export/import asymmetry**: The export format and the import endpoint use slightly different structures; should be unified.
- **Metadata not in case list**: The list-cases endpoint omits metadata from the response; requires a separate get-case call per case.
- **Error message formatting**: Some API error responses return raw internal messages; should be user-friendly.
