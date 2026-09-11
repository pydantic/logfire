---
name: logfire-evals
description: Run offline evaluations for Python (`pydantic_evals`) or Node.js (`logfire/evals`) and review experiments in Logfire. Also redirects existing Braintrust `Eval()` suites. Use for evaluation setup, test datasets, AI scoring, agent-behavior checks, LLM judges, Braintrust migration, or Logfire Datasets & Experiments. Do not use for live production traffic or infrastructure monitoring.
---

# Evaluate AI code with Logfire

## How This Works

Python's `pydantic_evals` and Node.js's `logfire/evals` run the real task against cases, apply evaluators, and return a report. An active Logfire or OpenTelemetry provider may export evaluation inputs and outputs even if this skill did not configure it. Uploading intentionally needs `logfire.configure()` in Python or a configured exporter in Node.js.

Span-based evaluators inspect the task's OpenTelemetry span tree. Without working Logfire instrumentation, Python reports "No span tree available"; Node.js `HasMatchingSpan` can produce no evaluator result at all. Treat either signal as a setup failure, not evidence about the agent.

## Step 1: Check for an Existing Braintrust Suite First

Cheap check, before anything else: does this repo already have an existing Braintrust suite — actual `Eval(...)` calls or `from braintrust import Eval` in source, not just a `braintrust` dependency listed without any real usage? This path needs **no CLI auth at all** — don't run Step 2 for it. The compatibility endpoint is documented only for Logfire Cloud US and EU; for any other supplied origin, use the native evaluation path instead.

Keep the existing `Eval()` code (Python `braintrust>=0.30.1` / TypeScript `braintrust>=3.24.0` — verified versions) and redirect its next run to Logfire by changing environment variables only, no `pydantic_evals` involved:

```bash
export BRAINTRUST_APP_URL="https://logfire-us.pydantic.dev/v1/braintrust"  # EU: logfire-eu.pydantic.dev
export BRAINTRUST_API_KEY="<logfire-project-api-key>"                     # Settings -> API Keys
unset BRAINTRUST_API_URL BRAINTRUST_PROXY_URL  # these override the endpoint above if set — the #1 "it still hit Braintrust" cause
```

The API key must belong to the destination project and include `project:write_otlp` and `project:read_datasets`. The SDK writes the run, then reads experiment metadata for its comparison summary; an ingest-only write token fails that read with `403`.

This is a **compatibility preview, not full parity**: covers inline/callable data, local tasks and scorers, multiple scores, one label per name, and normal summary finalization. It does not cover Braintrust-hosted datasets/prompts/functions, BTQL, the model proxy, server-side scoring, or post-finalization feedback — and `summarize_scores=False`, a manual `flush()` without a comparison, or the Rust SDK never request the summary this endpoint needs, so nothing lands even though the run appears to succeed. Full detail and the concept-translation table (Braintrust "project" → Logfire dataset name, "scorer" → evaluator, etc.): https://pydantic.dev/docs/logfire/get-started/comparisons/migrate-from-braintrust/.

Skip straight to Step 5 (Verify) — the SDK's own printed result URL also opens directly in Logfire, and nothing else here (auth, dataset definition) applies to this path.

**No existing Braintrust suite? Continue to Step 2 now**, before the more detailed identification in Step 3 — nothing past this point requires knowing the function/agent or dataset shape yet.

## Step 2: Authenticate When the Run Needs Logfire

Skip authentication and continue to Step 3 only when the user explicitly wants a local-only run using evaluators that do not need span data. Run it in a fresh process that neither preloads nor imports the application's telemetry setup; omit Python's `logfire.configure()` and any Node.js exporter bootstrap. Inspect the task's imports first: if it configures an exporter itself and the repository has no documented disable switch, stop rather than claiming the run is local-only. Uploading results, using a hosted dataset, or running a span-based evaluator requires Logfire, so authenticate before running the evaluation and target the exact project first.

For a Logfire-backed run, use [Authenticate and Select the Exact Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md) to derive the CLI target from the supplied Logfire URL and run its target-aware `whoami` check. Skip to Step 3 if that already reports the right project and resolved `--region` or `--base-url` target; otherwise, continue through the full authentication and project-selection sequence there. This CLI flow is for `logfire.configure()`; Step 3's hosted-dataset operations use a separate API key with different scopes.

## Step 3: Detect What to Evaluate

Identify the real task and any existing dataset. Follow repository package, test, and dependency conventions. For a first evaluation, prefer 3-5 cases from existing tests, schemas, examples, or synthetic fixtures, with deterministic checks for defined behavior. Do not copy the example unless it fits, replace an evaluation framework, or refactor unrelated code. If there is no runnable task or safe expected behavior, ask one focused question instead of inventing either.

- **In-code dataset**: a Python module using `pydantic_evals`, or a Node.js module using `logfire/evals`. This is the default for an agent-driven workflow.
- **Hosted/managed dataset**: cases live in the Logfire UI, edited by non-engineers, pulled/pushed via a separate `LogfireAPIClient` (`from logfire.experimental.api_client import LogfireAPIClient`). `client.get_dataset(name)` with no type arguments returns a raw dict, not something `push_dataset` or `.evaluate_sync()` can take — pass the input/output (and metadata, if used) types to get back a real `pydantic_evals.Dataset`: `client.get_dataset(name, MyInputType, MyOutputType)`. If the stored dataset contains custom evaluators, also pass their classes with `custom_evaluator_types=[MyEvaluator]` (and custom report evaluators with `custom_report_evaluator_types=[...]`) so they can be deserialized. Push with `client.push_dataset(dataset)`. This needs its own API key from **Settings → API Keys** (scoped `project:read_datasets`/`project:write_datasets`), not Step 2's CLI auth flow. Only relevant if the user specifically wants case editing outside code.

## Step 4: Define the Dataset and Run It

Use the repository's existing package manager. Install only the missing integration for its language.

### Python

```bash
uv add 'pydantic-evals[logfire]'
```

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
```

Use `logfire[datasets]` instead only when the task specifically needs the hosted-dataset API from Step 3.

### JavaScript or TypeScript on Node.js

Add `logfire` and the Node exporter if missing:

```bash
npm install logfire @pydantic/logfire-node
```

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

dataset.evaluate(classifySentiment).then((report) => {
  console.log(renderReport(report, { includeInput: true, includeOutput: true }))
})
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
smoke.evaluate(classifySentiment).then((report) => {
  console.log(renderReport(report, { includeInput: true, includeOutput: true }))
})
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

**Came from the Step 1 Braintrust path (Step 2 skipped)?** There's no `whoami`-resolved project to look up here — use the SDK's own printed result URL instead, which already opens directly in the right Logfire project. Confirm the same things below (completion, pass mix, case detail) from that page rather than searching by name.

1. **Query for the run directly, if a Logfire MCP server or API is connected** — the root span for a run is named `evaluate {name}` and carries `gen_ai.operation.name = 'experiment'`, `dataset_name`, and `task_name` attributes; find the most recent one matching your dataset's name and confirm `logfire.experiment.metadata` shows the case count and pass rate you expect. Otherwise, open **AI Evaluations → Datasets & Experiments → Experiments** in Logfire for the exact project from Step 2, and find the run by name/timestamp.
2. **Read the Overview tab (or the queried metadata) first**: completion count, assertion pass mix, task errors, average duration. **If completion says "Not reported,"** the run sent case data but never signaled it finished — treat that as a broken run, not a passing one.
3. **Open the Cases tab**, starting from Needs Review / Failed / Errors, not the full list.
4. **Drill into a failing case's trace in Live view** for the actual evidence, rather than trusting the summary score alone.
5. **Fix and re-run** until the cases that should pass do, and any tool-call/trajectory checks show real span data, not "No span tree available."

Close with a final report built from what you just confirmed — the run name, exact case count and pass rate you queried, and which evaluators ran — not a template. **Include the direct link to this experiment** (the SDK's own printed result URL, or the Datasets & Experiments page you opened it from), so the user can see the run without having to ask where to look.
