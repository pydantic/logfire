---
name: logfire-datasets
description: Build or extend a hosted dataset stored in Logfire by uploading cases extracted from Logfire traces, spans, logs, or query results, or from existing case files. Use when the user asks to "create a hosted dataset in Logfire", "upload cases to Logfire", "turn Logfire traces into dataset cases", "add cases to a Logfire dataset", "push a dataset to Logfire", or "list/fetch hosted datasets". The Logfire MCP server has no dataset tools; this skill uses an API key and the Python SDK. Not for writing or running evaluations, evaluators, or experiments, or for local pydantic_evals datasets: use logfire-evals for those.
---

# Create Logfire Datasets

## How This Works

A hosted dataset is a named collection of cases in one Logfire project. Each case has
`inputs` (required), and optional `expected_output`, `metadata`, `name`, `tags`, and a
link to the trace it came from. Experiments (run with `pydantic_evals`) read these cases.

The Logfire MCP server can query telemetry but **cannot read or write datasets**. Dataset
work goes through `logfire.experimental.api_client` (install `logfire[datasets]`),
authenticated with a Logfire **API key**. Neither the MCP OAuth session nor a
`LOGFIRE_TOKEN` write token can be used for it.

The workflow is: configure credentials, agree on the case shape, discover the source data,
write a retrieval and upload script for the project, dry-run it, push, verify.

## Step 1: Configure Credentials

Two different credentials are involved. They are not interchangeable:

| Credential | Variable | Used for | Where it comes from |
|------------|----------|----------|---------------------|
| API key | `LOGFIRE_API_KEY` | Datasets API (`LogfireAPIClient`): needs `project:read_datasets` and `project:write_datasets` | **Settings > API Keys** in the project that will hold the dataset |
| Read token | `LOGFIRE_READ_TOKEN` | Querying telemetry from a script (`LogfireQueryClient`) | The Logfire CLI (`read-tokens create`, below), or **Settings > Read tokens** in the project holding the traces |

The query API accepts only read tokens. An API key fails there with `401 Invalid read token`,
even when it has `project:read`. The dataset is created in **the project the API key belongs
to**. Neither credential spans projects. The region (US/EU) is inferred from each credential.
Set `LOGFIRE_BASE_URL` only for self-hosted Logfire.

A read token is not needed when there is no script-side query: for example, the cases already
exist in code, or the set is small enough to export with MCP `query_run` into a JSON file that
the script reads instead of querying. That route passes trace content through the agent's
context, so keep it to a few dozen rows.

The user always creates the credentials (API keys only in the UI). Use this handoff every time:

**Where credentials live.** Dataset scripts resolve each variable in this order, and stop with a
message naming the variable, the project, and the scopes if neither is found:

1. The process environment (CI, or a shell the agent was launched from).
2. A `NAME=value` line in a gitignored `.env` file at the project root.

**Procedure:**

1. Check where each variable is set, without printing values. Run this from the project root:

   ```bash
   python3 -c "import os,re,pathlib; p=pathlib.Path('.env'); t=p.read_text() if p.exists() else ''
   for k in ['LOGFIRE_API_KEY','LOGFIRE_READ_TOKEN']:
       m=re.findall(rf'^\s*(?:export\s+)?{k}\s*=(.*)$', t, re.M)
       v=m[-1].strip().strip('\'\"') if m else None
       print(k, 'environment' if os.environ.get(k) else '.env' if v else 'empty line in .env' if m else 'missing')"
   ```

   A value from the **environment** wins over `.env` and may be left over from another
   project. Before using it, ask the user to confirm it is meant for this dataset. If
   everything needed is present and confirmed, go to the verification step below.
2. Otherwise, confirm with the user which project should hold the dataset (the API key decides
   it) and which project holds the traces.
3. Prepare the `.env` file: make sure it is ignored (`git check-ignore -q .env`; if it isn't,
   ask before adding `.env` to `.gitignore`). Add an empty `NAME=` line only for variables
   that have no line at all. If a line already exists (empty, quoted, or `export`-prefixed),
   have the user fill that one, because a second line for the same name overrides the first.
4. Hand off to the user with these exact details:
   - in project `<dataset project>`, **Settings > API Keys**, create a key named
     `datasets-<dataset name>` with `project:read_datasets` and `project:write_datasets`;
   - in project `<traces project>`, **Settings > Read tokens**, create a read token;
   - paste each after its variable in `<absolute path>/.env`.

   Explain that a variable exported in their own terminal now would not reach the agent's
   commands, which is why the credentials go in the file.
5. Wait for the user to confirm, then re-run the presence check.

**Read token from the Logfire CLI.** Instead of asking the user to create the read token in the
UI, the agent can mint it with the Python Logfire CLI. First authenticate and select the target
with [Authenticate and Select the Exact Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md):
derive `<target>` (`--region` or `--base-url`), use its verified CLI prefix, and run its
`whoami` check. Skip the rest of that reference if `whoami` already reports a signed-in user.
`read-tokens create` prints the token to stdout, so capture it straight into `.env` and never
let it reach the terminal or transcript:

```bash
# <logfire> = auth.md's verified Python CLI prefix, including --non-interactive <target>
token="$(<logfire> read-tokens --project '<org>/<traces project>' create)" \
  && printf 'LOGFIRE_READ_TOKEN=%s\n' "$token" >> .env; unset token
```

Run it only when `.env` has no `LOGFIRE_READ_TOKEN` line. If an empty one exists, remove it
first, because a second line overrides the first. Do not use `--save`: it stores the token under
`.logfire/`, where dataset scripts don't look. The API key still has to come from the UI.

Never ask for a credential in chat, never print or log it (not even a prefix), and never write
it into a tracked file. Do not take credentials from other tools' config files unless the user
points you to them. When a credential is in a different `.env` than the script expects, pass it
into the script's environment for that command instead of copying it to another file.

**Then:**

1. Add `logfire[datasets]` to the project's dependencies (for example
   `uv add 'logfire[datasets]'`).
2. Verify the credentials before writing anything else. Run a trivial query with
   `LogfireQueryClient` and the read token, and call `LogfireAPIClient.list_datasets()` with the
   API key (proves `project:read_datasets`). Both are read-only. A `401` means the credential is
   wrong, the wrong kind, or for another region; a `403` names the missing scope.
   `project:write_datasets` is only proven by the first push. Build this into the script as a
   check stage (Step 4) so it can be re-run.
3. Confirm the API key belongs to the intended project. Every dataset returned by
   `list_datasets()` carries a `project_id`. Compare it with the project's id (MCP
   `project_list` shows ids) or ask the user. If the project has no datasets yet, the
   `create_dataset()` response carries `project_id`: the script must check it before adding
   any cases, and on a mismatch stop and tell the user. The empty dataset it created in the
   wrong project should then be deleted, with the user's OK.

## Step 2: Agree on the Case Shape

Before querying, settle with the user what the dataset is for, because that decides what goes
where:

- **`inputs`**: exactly what the task under test will receive, including any context it
  depends on.
- **`expected_output`**: a reference answer, or omit it. A production output is only a correct
  reference if someone has reviewed it. Unreviewed outputs are better kept in `metadata`
  (for example `metadata.observed_output`) for regression checks.
- **`metadata`**: anything the user will want to slice results by later, such as the service or
  environment a row came from.

Use **JSON objects** for `inputs`, `expected_output`, and `metadata`. The hosted API rejects a
bare scalar `expected_output` (`dict_type: Input should be a valid dictionary`). Wrap scalars,
for example `{"value": ...}`, and make the eval task compare against that field.

Pick a stable dataset name: it starts with a letter or digit and uses only letters, digits,
`.`, `_` and `-`. Names are unique per project. Reuse the name the eval code will use, because a
hosted and a code-defined dataset with the same name merge into one entry.

## Step 3: Discover the Source Data

Do the exploration with the MCP `query_run` tool if it is available (no credentials needed).
Otherwise run each query through `LogfireQueryClient.query_json_rows()` with the read token (see
[references/python-scripts.md](references/python-scripts.md#retrieving-rows)).

Follow the discovery sequence in [references/trace-extraction.md](references/trace-extraction.md):

1. Inventory spans to find the one whose lifetime brackets one unit of the behaviour the
   dataset is about.
2. List its attribute keys and check how often each is populated.
3. Sample a few truncated values to learn each value's shape.
4. If inputs and outputs live on different spans, relate them through the trace tree.

Never assume span names, attribute keys, or payload shapes, even for instrumentation you
recognise. Versions and configuration change them. Before writing the extraction query, list
the candidate rows with short excerpts and confirm with the user that the selection matches
what they meant.

Check how many candidate rows have content replaced by Logfire's scrubber (`[Scrubbed due to
'...']`). That content is gone. Exclude those rows and report the count to the user.

Production traces can contain personal or customer data, and a dataset copies it into a
long-lived store. If inputs look like they hold PII or secrets, tell the user before pushing and
offer to redact or drop fields when mapping rows to cases.

## Step 4: Write and Dry-Run the Script

Write a Python script in the user's project, following its layout and tooling, that retrieves
the rows, maps them to cases, and uploads them. Read
[references/python-scripts.md](references/python-scripts.md) before writing it. It covers the
query and dataset clients, credentials, the stages the script needs, the case dict format,
local validation, and push behaviour.

The script must:

- read keys from the environment and fail clearly when one is missing;
- have a read-only check stage, a default dry run that writes a local preview, and write only
  behind an explicit flag such as `--push`;
- query a bounded window (at most 14 days per query) with SQL that returns one row per case,
  including `trace_id` and `span_id`;
- give every case a stable `name` (for example from `span_id`) so re-runs upsert instead of
  duplicating;
- create the dataset only if it is missing, then upload with `add_cases()` using dicts that
  carry `source_trace_id` / `source_span_id`. On an existing dataset, `push_dataset()`
  overwrites evaluators, schemas, and description, and it cannot set trace links;
- check the dataset's `project_id` against the intended project before adding cases;
- validate cases locally before any write, and print the hosted `case_count` at the end.

Run the check, then the dry run. Show the user the case count and two or three cases from the
preview, and **get explicit confirmation before pushing**. Pushing writes to a shared project.
Keep the preview file out of git; it contains trace content.

When the cases already exist in code (a `pydantic_evals.Dataset` or a `.yaml`/`.json` case
file) and there is no trace link to keep, `push_dataset()` on that dataset is the shorter path.
See the reference.

## Step 5: Verify

Never report a dataset as created or populated without checking it in this session.

1. Confirm the hosted `case_count` the script printed matches the preview. A lower count means
   names collided. A higher count means the dataset already held cases (neither upload path
   deletes cases).
2. Spot-check content with `list_cases(name)` or `get_dataset(name)`.
3. Point the user to **AI Evaluations > Datasets & experiments > Datasets** in the target
   project. Cases created with `source_trace_id` link back to their trace.

Close with the dataset name, project, hosted case count, the script path, and the exact command
to re-run it. To run an experiment over the dataset next, use
[`logfire-evals`](https://pydantic.dev/.well-known/agent-skills/logfire-evals/SKILL.md).

## Limits

- 10,000 cases per dataset. Updating a named case does not consume capacity. Unnamed cases
  always count as new and duplicate on every re-run.
- An import that would exceed the limit is rejected entirely. Split large collections across
  datasets.
- Cases are validated against the dataset's JSON schemas on write. Schemas do not apply
  retroactively.
- Telemetry queries cover at most 14 days per call. For a longer history, query several
  windows and merge on `span_id`.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Trying MCP tools or `LOGFIRE_TOKEN` for dataset calls | Use an API key with the datasets scopes |
| `401 Invalid read token` from `LogfireQueryClient` | The query API needs a read token, not an API key |
| Dataset appears in the wrong project | The key decides the project. Use a key from the target project |
| `dict_type: Input should be a valid dictionary` | Wrap scalar `expected_output` (or inputs/metadata) in an object |
| Duplicate cases after re-running | Give every case a stable `name` (for example from `span_id`) |
| Using unreviewed production output as `expected_output` | Put it in `metadata`, or have the user review it first |
| Overwriting evaluators configured in the UI | Use `add_cases()` for existing datasets, not `push_dataset()` |
| Expecting local deletions to propagate | Neither upload path deletes; call `delete_case()` explicitly |
| Guessing attribute names in SQL | Run the discovery queries first |
