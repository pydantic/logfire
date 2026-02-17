---
title: "SDK Reference"
description: "Complete method and exception reference for the Logfire datasets SDK."
---

# SDK Reference

!!! warning "Experimental Feature"

    Managed datasets are an experimental feature currently gated behind a feature flag. Reach out to us on [Slack](https://logfire.pydantic.dev/docs/join-slack/) or [contact us](../../../help.md) to learn how to enable it for your project.

For usage examples, see the [SDK Guide](sdk.md).

## LogfireAPIClient

| Method | Description |
|--------|-------------|
| `list_datasets()` | List all datasets in the project. |
| `get_dataset(id_or_name)` | Get a dataset by UUID or name. |
| `create_dataset(name, *, input_type, output_type, metadata_type, description, guidance)` | Create a new dataset. Types are converted to JSON schemas automatically. |
| `update_dataset(id_or_name, *, name, input_type, output_type, metadata_type, description)` | Update a dataset's metadata or schemas. |
| `delete_dataset(id_or_name)` | Delete a dataset and all its cases. |
| `list_cases(dataset_id_or_name, *, tags)` | List all cases in a dataset. Optionally filter by tags. |
| `get_case(dataset_id_or_name, case_id)` | Get a specific case. |
| `add_cases(dataset_id_or_name, cases, *, tags, on_conflict)` | Add cases to a dataset. Accepts `pydantic_evals.Case` objects or plain dicts. Uses upsert by default (`on_conflict='update'`): cases with matching names are updated. Set `on_conflict='error'` to fail on conflicts. |
| `update_case(dataset_id_or_name, case_id, *, name, inputs, expected_output, metadata, evaluators, tags)` | Update an existing case. |
| `delete_case(dataset_id_or_name, case_id)` | Delete a case. |
| `export_dataset(id_or_name, input_type, output_type, metadata_type)` | Export as a typed `pydantic_evals.Dataset`. |

An async version, `AsyncLogfireAPIClient`, provides the same methods as async coroutines.

## Exceptions

| Exception | Description |
|-----------|-------------|
| `DatasetNotFoundError` | Raised when a dataset lookup by ID or name finds no match. |
| `CaseNotFoundError` | Raised when a case lookup finds no match. |
| `DatasetApiError` | Raised for other API errors. Contains `status_code` and `detail`. |
