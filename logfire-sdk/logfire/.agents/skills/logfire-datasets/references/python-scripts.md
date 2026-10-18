# Writing a Dataset Script in Python

How to write a script that retrieves source data from Logfire, maps it onto cases, and
uploads it as a hosted dataset. Fit the script to the project's layout, tooling, and data.
The snippets below show individual SDK calls; they are not a template to copy whole.

## Dependencies and Imports

Add `logfire[datasets]` to the project (`uv add 'logfire[datasets]'`, or the project's
equivalent). The extra brings `httpx` and `pydantic-evals`. Both clients below exist in
`logfire>=4.39`; check the project's pinned version before relying on them.

The names used below:

- `logfire.query_client`: `LogfireQueryClient` (or `AsyncLogfireQueryClient`).
- `logfire.experimental.api_client`: `LogfireAPIClient` (or `AsyncLogfireAPIClient`),
  `DatasetNotFoundError`, `CaseNotFoundError`, and `DatasetApiError`.

`api_client` is experimental. Its API may change between releases.

## Credentials

Neither client reads environment variables on its own. Resolve each credential in the order
SKILL.md defines, then pass it explicitly:

1. The process environment.
2. A `NAME=value` line in the project's gitignored `.env`. Look for `.env` in the current
   working directory or the project root, not next to the script file, because scripts often
   live in a subdirectory.

`python-dotenv`'s `load_dotenv()` does this: it does not override variables that are already
set. A hand-written parser must match what dotenv accepts: an optional `export ` prefix,
whitespace around `=`, quoted values, and the last line winning when a name repeats. Never hard-code a credential or accept it as a CLI argument, because it would end
up in shell history.

| Variable | Client | What it must be |
|----------|--------|-----------------|
| `LOGFIRE_API_KEY` | `LogfireAPIClient(api_key=...)` | An API key from the project that will hold the dataset, with `project:read_datasets` and `project:write_datasets` |
| `LOGFIRE_READ_TOKEN` | `LogfireQueryClient(read_token=...)` | A read token for the project holding the traces. An API key is rejected here with `401 Invalid read token` |
| `LOGFIRE_BASE_URL` | Both, as `base_url=` | Self-hosted Logfire only |

Both clients infer the region (US/EU) from the credential. If one is missing, fail with a
message that names the variable, what kind of credential it is, and where to create it. That
message is the most useful thing the script can tell a user who has not set it up.

## Script Stages

Give the script these stages, in this order, with writing only behind an explicit flag:

1. **Check:** prove the credentials before doing work. Run a trivial query with the read
   token, and call `list_datasets()` with the API key to prove `project:read_datasets`. Both
   are read-only. Print the `project_id` of the listed datasets so it can be compared with the
   intended project. `project:write_datasets` can only be proven by the first write.
2. **Retrieve:** run the extraction SQL over a bounded time window.
3. **Map:** turn each row into a case dict, or skip it.
4. **Validate:** check every case locally, before any network write.
5. **Preview (default):** write the cases to a local file and print the count. Show the user
   a few of them and get confirmation before uploading.
6. **Push (`--push` or similar):** create the dataset if it is missing, then upsert cases.
7. **Verify:** read back the hosted `case_count` and print it with the dataset id.

A single `--check` flag, a default dry run, and a `--push` flag cover this. Keep the
query and the mapping near the top of the file, because they are what changes when someone
adapts the dataset later.

## Retrieving Rows

```python
with LogfireQueryClient(read_token=read_token) as query:
    result = query.query_json_rows(sql=SQL, min_timestamp=start, max_timestamp=end)
rows = result['rows']        # list of dicts keyed by column name
```

- `read_token=` must be a read token. API keys are rejected with `401 Invalid read token`.
- **No read token?** For a small one-off set, export the rows with MCP `query_run` into a
  JSON file and give the script a `--rows <file>` option that skips the query. Everything after
  retrieval stays the same. Writing the file means re-typing the MCP result, so select
  `md5(<expr>)` next to each long text column in the export query and compare it with
  `hashlib.md5(text.encode()).hexdigest()` before pushing. Any mismatch means the copy is wrong.
- `min_timestamp` is effectively required: omitting it is deprecated. Use timezone-aware
  datetimes; naive ones are assumed to be UTC.
- One query spans at most 14 days. For a longer history, loop over windows of 14 days or less
  and dedupe on `span_id`.
- Do not pass `limit=` unless you mean it. It takes priority over the `LIMIT` in the SQL.
- `environment='production'` (or a list) restricts rows to a deployment environment
  without editing the SQL.
- Columns selected with `attributes->'key'` (a JSON subtree) can arrive as JSON-encoded
  strings. Decode them with `json.loads` before mapping. Columns selected with `->>` are
  plain text.
- `query_csv()` and `query_arrow()` (pyarrow) exist for large pulls or pandas work.
- Errors: `QueryExecutionError` (bad SQL) and `QueryRequestError` (bad request).

The SQL itself should return one row per case and include `trace_id` and `span_id`. See
[trace-extraction.md](trace-extraction.md) for discovery and extraction queries.

## Mapping Rows to Cases

`add_cases()` accepts plain dicts with these keys:

| Key | Required | Notes |
|-----|----------|-------|
| `inputs` | yes | JSON object. Exactly what the task under test receives |
| `name` | strongly recommended | Stable and unique, for example `f"span-{row['span_id']}"`. It makes re-runs update cases instead of duplicating them |
| `expected_output` | no | JSON object. The API rejects a bare scalar. Wrap it, for example `{"value": ...}` |
| `metadata` | no | JSON object of whatever the user will want to slice results by |
| `source_trace_id`, `source_span_id` | no | Links the case to its trace in the UI. Only the dict form can set these |
| `tags` | no | List of strings |

Drop keys whose value is `None` instead of sending nulls. Return nothing (skip) for rows
that lack the inputs. Do the redaction for PII or secrets here, so that it happens before
anything leaves the machine.

## Validating Before Upload

The server validates cases against the dataset's JSON schemas and rejects a whole request
when one case fails. Catch problems locally first, so the error names the row:

- `inputs` is present and is a dict. `expected_output` and `metadata` are dicts when present.
- Names are unique. Two rows with the same name silently become one case, so warn about it.
- If the dataset has typed schemas, validate each field with `pydantic.TypeAdapter(Model)`
  using the same models passed to `create_dataset`.
- The total stays at or below 10,000 cases, counting cases already in the dataset that
  are not being updated.

Unnamed cases always count as new, so they duplicate on every re-run. Warn when there are any.

## Pushing

```python
with LogfireAPIClient(api_key=dest_key) as client:
    try:
        detail = client.get_dataset(NAME, include_cases=False)   # exists: leave its settings alone
    except DatasetNotFoundError:
        detail = client.create_dataset(NAME, description=DESCRIPTION)  # schemas: see below
    if str(detail.get('project_id')) != EXPECTED_PROJECT_ID:
        sys.exit(f'{NAME} is in project {detail.get("project_id")}, not {EXPECTED_PROJECT_ID}')
    for batch in batches(cases, 200):
        client.add_cases(NAME, batch, on_conflict='update')
    detail = client.get_dataset(NAME, include_cases=False)
```

- **Create only if missing.** Do not call `update_dataset()` or `push_dataset()` on an
  existing dataset unless the user asked to change its settings. On an existing dataset,
  `push_dataset()` replaces dataset-level evaluators, its input/output/metadata schemas
  (taken from the `Dataset`'s generic types), and its description when one is passed. Any of
  these may have been set by teammates in the UI.
- **Check the project before adding cases.** The API key decides the project. Compare
  `project_id` on the existing or newly created dataset with the intended project's id
  (`EXPECTED_PROJECT_ID` above, taken from MCP `project_list` or from the user), and stop on a
  mismatch.
- `create_dataset(input_type=, output_type=, metadata_type=)` takes pydantic models or
  dataclasses and stores their JSON schemas. Add them only once the case shape is stable,
  because schemas reject later cases that don't match.
- `add_cases(..., on_conflict='update')` upserts by name (the default). `'error'` fails on
  existing names, which suits a strictly append-only dataset.
- **Batch the upload.** Each `add_cases` request is all-or-nothing. A few hundred cases per
  request keeps payloads reasonable, and because named cases upsert, a failed run can simply
  be re-run. An upsert creates a new case `version` even when the content is unchanged.
- Neither `add_cases` nor `push_dataset` deletes anything. Removing stale cases means
  `list_cases()` followed by `delete_case()` per id. Confirm with the user first.
- Catch `DatasetApiError` and report `.status_code` and `.detail`: `401` is the wrong key
  or region, `403` is a missing scope, and `409` from `create_dataset` means the name
  exists. For schema or payload failures, `.detail` names the failing field.

**When the cases already live in code** (a `pydantic_evals.Dataset` or a case file) and
there is no trace link to keep, `push_dataset()` is the shorter path. It creates or updates
the dataset, sets schemas from the dataset's generic types, replaces dataset-level
evaluators, and upserts named cases. Use it for a new dataset, or when the user wants the code
to own those settings:

```python
dataset = Dataset[MyInputs, MyOutput, MyMetadata].from_file('cases.yaml')
with LogfireAPIClient(api_key=dest_key) as client:
    client.push_dataset(dataset, description=DESCRIPTION)
```

For an existing dataset whose settings the user wants to keep, upload `dataset.cases` with
`add_cases()` instead.

## Reading Datasets Back

| Call | Returns |
|------|---------|
| `list_datasets()` | Summaries: `id`, `name`, `description`, `case_count` |
| `get_dataset(name, include_cases=False)` | Metadata and schemas, with `case_count` |
| `get_dataset(name)` | Raw export dict (`name`, `cases`, `evaluators`). Safe even when stored evaluators are custom classes |
| `get_dataset(name, InputT, OutputT, MetaT, custom_evaluator_types=[...])` | A typed `pydantic_evals.Dataset`, ready for `evaluate()`. Fails if the stored evaluators include classes it was not given |
| `list_cases(name)` / `get_case(name, case_id)` | Full case details, including ids, `source_trace_id`, and version |

Every `name` argument also accepts the dataset UUID. A response that doesn't match the
SDK's types comes back as a raw dict with a `UserWarning`; upgrading `logfire` fixes that.

## Async Code

Inside an async application (FastAPI handlers, async workers), use
`AsyncLogfireQueryClient` and `AsyncLogfireAPIClient` with `async with` and `await`. The
methods and arguments are the same. The sync clients block the event loop.
