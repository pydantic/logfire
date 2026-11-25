---
name: logfire-evals
description: Run offline Python (`pydantic_evals`) or Node.js (`logfire/evals`) evaluations and review them in Logfire. Also redirect existing Braintrust `Eval()` suites. Use for eval setup, test datasets, AI scoring, agent checks, LLM judges, Braintrust migration, or Logfire Datasets & Experiments. Not for live traffic or infrastructure monitoring.
---

# Evaluate AI code with Logfire

## How This Works

Python's `pydantic_evals` and Node.js's `logfire/evals` run a task against cases, apply evaluators, and return a report. An active Logfire or OpenTelemetry provider may export inputs and outputs even if this skill did not configure it. Intentional upload needs `logfire.configure()` in Python or a configured Node.js exporter.

Span-based evaluators inspect the task's OpenTelemetry span tree. Without working Logfire instrumentation, Python reports "No span tree available"; Node.js `HasMatchingSpan` can produce no evaluator result at all. Treat either signal as a setup failure, not evidence about the agent.

## Step 1: Check for an Existing Braintrust Suite First

Cheap check, before anything else: does this repo already have an existing Braintrust suite — actual `Eval(...)` calls or `from braintrust import Eval` in source, not just a `braintrust` dependency listed without any real usage? This path needs no CLI auth when a suitable project API key already exists. The compatibility endpoint is documented only for Logfire Cloud US and EU; for any other supplied origin, use the native evaluation path instead.

Keep the existing `Eval()` code (Python `braintrust>=0.30.1` / TypeScript `braintrust>=3.24.0`) and redirect its next run to Logfire by changing environment variables only, no `pydantic_evals` involved:

```bash
export BRAINTRUST_APP_URL="https://logfire-us.pydantic.dev/v1/braintrust"  # EU: logfire-eu.pydantic.dev
unset BRAINTRUST_API_URL BRAINTRUST_PROXY_URL  # these override the endpoint above if set
```

Supply `BRAINTRUST_API_KEY` through the project's private environment or secret
manager; never paste the key into a shell command, source file, or chat.
The destination project's API key needs `project:write_otlp` and `project:read_datasets`: the SDK writes the run, then reads experiment metadata for its summary. An ingest-only write token fails with `403`.

If a new key is authorized, run the exact CLI in the confirmed project's application
directory. For example, the arguments for Cloud US/organization acme are
`--region us --org acme --no-input --output json api-key project:write_otlp project:read_datasets --name braintrust`.
Substitute the confirmed origin and organization. The project comes from the
validated local credential directory, not a `--project` flag. Capture raw stdout
directly into the private environment; do not display it.

This **compatibility preview** covers inline/callable data, local tasks and scorers, multiple scores, one label per name, and normal summary finalization. It excludes Braintrust-hosted resources, BTQL, the model proxy, server-side scoring, and post-finalization feedback. Rust, `summarize_scores=False`, and manual `flush()` without comparison do not request the summary needed for projection. See the [full coverage and concept mapping](https://pydantic.dev/docs/logfire/get-started/comparisons/migrate-from-braintrust/).

Skip straight to Step 5 (Verify) — the SDK's own printed result URL also opens directly in Logfire, and nothing else here (auth, dataset definition) applies to this path.

**No existing Braintrust suite? Continue to Step 2 now**, before the more detailed identification in Step 3 — nothing past this point requires knowing the function/agent or dataset shape yet.

## Step 2: Authenticate When the Run Needs Logfire

For an explicitly local-only run without span evaluators, use a fresh process that neither preloads nor imports application telemetry; omit Python's `logfire.configure()` and any Node.js exporter bootstrap. If the task configures an exporter and has no documented disable switch, stop rather than claiming local-only. Uploading, hosted datasets, and span evaluators require Logfire authentication to the exact project.

For a Logfire-backed run, reuse the exact target and project if the parent
wizard already prepared them. Otherwise, use [Authenticate and Select the Exact
Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md) for the Rust
CLI's target-aware identity check, OAuth session, and explicit project selection.
This CLI flow is for `logfire.configure()`; Step 3's hosted-dataset operations
use a separate API key with different scopes.

## Step 3: Detect What to Evaluate

Identify the real task and any dataset. Follow repository package, test, and dependency conventions. For a first eval, prefer 3-5 cases from tests, schemas, examples, or synthetic fixtures, with deterministic checks for defined behavior. Do not copy the example unless it fits, replace an eval framework, or refactor unrelated code. Without a runnable task or safe expected behavior, ask one focused question instead of inventing either.

- **In-code dataset**: a Python module using `pydantic_evals`, or a Node.js module using `logfire/evals`. This is the default for an agent-driven workflow.
- **Hosted/managed dataset**: cases live in the Logfire UI and can be edited
  outside the codebase. Use this only when the user specifically wants that
  workflow.

### Hosted dataset requirements

Import `LogfireAPIClient` from `logfire.experimental.api_client`. Hosted inputs
and outputs must be JSON objects; unlike code-defined datasets, scalar roots are
rejected.

`client.get_dataset(name)` without type arguments returns a raw dictionary. To
get a `pydantic_evals.Dataset` that supports `push_dataset` and
`.evaluate_sync()`, pass the input and output types, plus the metadata type when
used:

```python
client.get_dataset(name, MyInputType, MyOutputType)
```

When the dataset has typed metadata, pass its type as the next argument.

If the stored dataset has custom evaluators, pass their classes with
`custom_evaluator_types=[MyEvaluator]`. Use
`custom_report_evaluator_types=[...]` for custom report evaluators. Push changes
with `client.push_dataset(dataset)`.

Hosted dataset access needs a separate API key. If authorized to mint one, use
the same confirmed application directory, target, organization, non-interactive
flags, and private stdout capture as the Step 1 example. Use
`api-key project:read_datasets --name hosted-evals` for reads; add
`project:write_datasets` only for create/update/push. CLI login is not this key.

## Step 4: Define the Dataset and Run It

Use the repository's existing package manager and lockfile. Install only the missing integration for its language.

### Python

Add `pydantic-evals[logfire]` with the detected Python manager: `uv add`, `poetry add`, or `pdm add`. For a pip/requirements project, update its declared requirements and install from that file; do not introduce a second manager or lockfile.

```python
import logfire
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EqualsExpected, IsInstance

logfire.configure()  # omit only in the isolated local-only process described above

def classify_sentiment(text: str) -> str:
    return 'positive' if 'love' in text else 'negative'


dataset = Dataset[str, str, None](
    name='sentiment-eval',
    cases=[
        Case(name='positive', inputs='I love this', expected_output='positive'),
        Case(name='negative', inputs='This is terrible', expected_output='negative'),
    ],
    evaluators=[EqualsExpected(), IsInstance(type_name='str')],
)

report = dataset.evaluate_sync(classify_sentiment)  # or `await dataset.evaluate(...)`
report.print(include_input=True, include_output=True)
print(logfire.url_from_eval(report))
```

Use `logfire[datasets]` instead only when the task specifically needs the hosted-dataset API from Step 3.

### JavaScript or TypeScript on Node.js

Do not apply this section to Deno, Bun, browsers, or workers; their exporter setup is not validated by this skill.

Add `logfire` and `@pydantic/logfire-node` with the manager selected by the existing lockfile: `pnpm add`, `yarn add`, `bun add`, or `npm install`. Do not introduce a second lockfile.

Configure Logfire before loading the task. Reuse an existing instrumentation entry point rather than configuring it twice.

```ts
import * as logfire from '@pydantic/logfire-node'
import { Case, Dataset, EqualsExpected, renderReport } from 'logfire/evals'

logfire.configure()

const classifySentiment = (text: string) => (text.includes('love') ? 'positive' : 'negative')
const dataset = new Dataset<string, string>({
  name: 'sentiment-eval',
  cases: [new Case({ name: 'positive', inputs: 'I love this', expectedOutput: 'positive' })],
  evaluators: [new EqualsExpected()],
})

await dataset.evaluate(classifySentiment).then((report) => {
  console.log(renderReport(report, { includeInput: true, includeOutput: true }))
}).finally(() => logfire.shutdown({ timeoutMillis: 5000 }))
```

Other built-ins include `Equals`, `Contains`, `IsInstance`, `MaxDuration`, `HasMatchingSpan`, and `LLMJudge`. Node.js custom evaluators extend `Evaluator`, and `LLMJudge` needs a judge callback. Use `@pydantic/logfire-node/datasets` only for hosted datasets.

### Smoke test before a paid or full run

**Before running the full dataset, run a smoke test on 2-3 cases** if the dataset is large or uses `LLMJudge` or any evaluator that makes billed model calls. This catches setup errors before they multiply cost across the dataset.

Python:

```python
smoke = Dataset(
    name=dataset.name,
    cases=dataset.cases[:3],
    evaluators=dataset.evaluators,
    report_evaluators=dataset.report_evaluators,
)
smoke_report = smoke.evaluate_sync(classify_sentiment)
smoke_report.print(include_input=True, include_output=True)
```

Node.js:

```ts
const smoke = new Dataset({
  name: dataset.name,
  cases: dataset.cases.slice(0, 3),
  evaluators: dataset.evaluators,
  reportEvaluators: dataset.reportEvaluators,
})
await smoke.evaluate(classifySentiment).then((report) => {
  console.log(renderReport(report, { includeInput: true, includeOutput: true }))
}).finally(() => logfire.shutdown({ timeoutMillis: 5000 }))
```

Confirm the smoke run has zero unexpected errors and the assertions that should pass do. Then, if the full dataset is large or uses paid model calls, tell the user the case count and which evaluators will make model calls, and get explicit confirmation before running the full dataset — don't run an expensive full pass on the strength of a clean smoke test alone without saying so.

The remaining details in this section are Python-specific. Custom evaluators inherit `Evaluator` and implement `evaluate`; use `@dataclass` for configurable fields and portable serialization. Case names must be unique within a dataset. The evaluators reached for most:

| Evaluator | Checks |
|-----------|--------|
| `Equals(value)` / `EqualsExpected()` | Exact match against a literal / `expected_output` (no-op if `expected_output` is unset — don't rely on it silently catching that) |
| `IsInstance(type_name)` | Output's type matches by name |
| `LLMJudge(rubric, model=None, score=False)` | Subjective or rubric-based judgment; makes billed model requests, so validate the rubric against human-reviewed examples before treating it as a quality gate |
| `ToolCorrectness(expected_tools, ...)` | Which tools an agent called — reads the span tree, so needs Step 2's `logfire.configure()` to work at all, not just to upload |

Also available: `Contains`, `MaxDuration`, `TrajectoryMatch`, `ArgumentCorrectness`, `MaxToolCalls`, `MaxModelRequests` — same span-tree dependency as `ToolCorrectness` for the tool/trajectory ones; see `pydantic_evals.evaluators` for the full set. These five agentic (span-based) evaluators need `pydantic-evals>=2.4.0` — on an older pin, check `pyproject.toml`/`uv.lock` and upgrade before reaching for them, since the import itself is what fails, not a silent no-op.

The `Python` evaluator (arbitrary code execution) was removed for security reasons — don't reach for it even if an older example references it.

If editing a hosted dataset: `client.push_dataset(dataset)` **overwrites** server-side evaluators on every push, including removing ones you deleted locally — don't push a stale local copy over a dataset others have edited in the UI.

## Step 5: Verify

A report printing to the terminal isn't proof it reached Logfire — confirm the run actually landed. **Never report a case as passed, a score, or a run as complete without having actually checked it in this session** — if a run fails, cancels, or produces no scores, report that failure plainly; never substitute an invented score or a manual guess at what the result "should" be.

**Came from the Step 1 Braintrust path (Step 2 skipped)?** There's no `project current`-resolved project to look up here — use the SDK's own printed result URL instead, which already opens directly in the right Logfire project. Confirm the same things below (completion, pass mix, case detail) from that page rather than searching by name.

1. **For a native Logfire-backed run only, query through the authenticated CLI.**
   Braintrust users continue at item 2 using their SDK's result URL. Replace the
   synthetic dataset and task names with the exact ones you just ran, keep the
   exact target/org/project from Step 2, and require a fresh completed root span:

   ```bash
   logfire --region us --org acme --no-input --output json mcp query run "SELECT start_timestamp, end_timestamp, trace_id, span_id, attributes->>'dataset_name' AS dataset_name, attributes->>'task_name' AS task_name, attributes->'logfire.experiment.metadata' AS experiment_metadata FROM records WHERE start_timestamp > now() - interval '15 minutes' AND end_timestamp IS NOT NULL AND parent_span_id IS NULL AND attributes->>'gen_ai.operation.name' = 'experiment' AND attributes->>'dataset_name' = 'sentiment-eval' AND attributes->>'task_name' = 'classify_sentiment' ORDER BY start_timestamp DESC LIMIT 5" --project my-app
   ```

   Confirm `logfire.experiment.metadata` reports the expected completion count
   and pass mix. If query access is unavailable, open the exact project URL from
   standalone `project current` or, after a parent-prepared wizard handoff,
   `project open --no-open` with the same target/org and `--no-input --output json`.
   Append `/evals` to the validated project URL, then find the run by name and
   timestamp under **Datasets & Experiments**.
2. **Read the Overview tab (or the queried metadata) first**: completion count, assertion pass mix, task errors, average duration. **If completion says "Not reported,"** the run sent case data but never signaled it finished — treat that as a broken run, not a passing one.
3. **Open the Cases tab**, starting from Needs Review / Failed / Errors, not the full list.
4. **Drill into a failing case's trace in Live view** for the actual evidence, rather than trusting the summary score alone.
5. **Fix and re-run** until the cases that should pass do, and any tool-call/trajectory checks show real span data, not "No span tree available."

Close with a final report built from what you just confirmed — the run name,
exact case count and pass rate you queried, and which evaluators ran — not a
template. Native Python `pydantic_evals` runs must print
`logfire.url_from_eval(report)`. For Braintrust compatibility and other SDK paths,
use their own verified result URL when they provide one. Otherwise, include the
exact project's Datasets & Experiments page plus the run name and timestamp; do
not claim a URL was printed when it was not.
