---
name: logfire-evals
description: Evaluate Python AI/agent code against a dataset of test cases using pydantic_evals, and review results in Logfire's Datasets & Experiments UI. Also covers redirecting an existing Braintrust Eval() suite to Logfire with no code changes. Use this skill whenever the user asks to "set up evals", "add an evaluation", "test my agent against cases", "write a dataset of test cases", "score my LLM output", "add an LLM judge", "check tool-call correctness", "send Braintrust evals to Logfire", "migrate from Braintrust", or mentions pydantic_evals, Braintrust, Datasets & Experiments, or evaluating AI/agent behavior against known inputs. The `pydantic_evals` workflow is Python-only; the Braintrust redirect also supports TypeScript suites, env-vars-only. Both are for scoring DEFINED test cases offline — not for instrumenting live production traffic (use `logfire-instrumentation` for that) and not for infrastructure monitoring (use `logfire-infrastructure`).
---

# Evaluate with pydantic_evals and Logfire

## How This Works

`pydantic_evals` runs your actual function or agent against a `Dataset` of `Case`s (input + expected output + metadata), scores each with one or more `Evaluator`s, and produces a report. It depends on `logfire` itself (the `datasets` extra pulls in the real SDK, not a mock), so whether `logfire.configure()` has run determines only whether results *also* upload to Logfire's Datasets & Experiments UI — omitting it keeps results entirely local and printed to the terminal, **silently, not an error**.

Agentic evaluators (tool-call correctness, trajectory matching) need more than that: they read the task's own execution span tree, so without a working `logfire.configure()` they don't just fail to upload — every case reports "No span tree available" and the check never ran at all.

## Step 1: Check for an Existing Braintrust Suite First

Cheap check, before anything else: does this repo already have an existing Braintrust suite — actual `Eval(...)` calls or `from braintrust import Eval` in source, not just a `braintrust` dependency listed without any real usage? This path needs **no CLI auth at all** — don't run Step 2 for it.

Keep the existing `Eval()` code (Python `braintrust>=0.30.1` / TypeScript `braintrust>=3.24.0` — verified versions) and redirect its next run to Logfire by changing environment variables only, no `pydantic_evals` involved:

```bash
export BRAINTRUST_APP_URL="https://logfire-us.pydantic.dev/v1/braintrust"  # EU: logfire-eu.pydantic.dev
export BRAINTRUST_API_KEY="<logfire-project-write-token>"                  # Project -> Settings -> Write tokens
unset BRAINTRUST_API_URL BRAINTRUST_PROXY_URL  # these override the endpoint above if set — the #1 "it still hit Braintrust" cause
```

This is a **compatibility preview, not full parity**: covers inline/callable data, local tasks and scorers, multiple scores, one label per name, and normal summary finalization. It does not cover Braintrust-hosted datasets/prompts/functions, BTQL, the model proxy, server-side scoring, or post-finalization feedback — and `summarize_scores=False`, a manual `flush()` without a comparison, or the Rust SDK never request the summary this endpoint needs, so nothing lands even though the run appears to succeed. Full detail and the concept-translation table (Braintrust "project" → Logfire dataset name, "scorer" → evaluator, etc.): https://pydantic.dev/docs/logfire/get-started/comparisons/migrate-from-braintrust/.

Skip straight to Step 5 (Verify) — the SDK's own printed result URL also opens directly in Logfire, and nothing else here (auth, dataset definition) applies to this path.

**No existing Braintrust suite? Continue to Step 2 now**, before the more detailed identification in Step 3 — nothing past this point requires knowing the function/agent or dataset shape yet.

## Step 2: Authenticate When the Run Needs Logfire

Skip authentication and continue to Step 3 only when the user explicitly wants a local-only `pydantic_evals` run using evaluators that do not need span data; omit `logfire.configure()` in Step 4 so results stay in the terminal. Uploading results, using a hosted dataset, or running a span-based evaluator such as `ToolCorrectness` requires Logfire, so authenticate before opening or running evaluation files and target the exact project first.

For a Logfire-backed run, check first — `uvx logfire --non-interactive whoami` (JS: `npx logfire whoami`) — and skip to Step 3 if it already reports the right project and region. Otherwise, follow the full command sequence, flags, and gotchas (the `--non-interactive` requirement, why `auth` won't open a browser for you, the `LOGFIRE_TOKEN`-vs-credentials-file conflict, and token-file safety) in [Authenticate and Select the Exact Project](../logfire-instrumentation/references/auth.md). This CLI flow is for `logfire.configure()`; Step 3's hosted-dataset operations use a separate API key with different scopes.

## Step 3: Detect What to Evaluate

Identify the function or agent under test (a PydanticAI agent, an LLM-calling function, any callable that takes an input and returns an output) and whether a dataset already exists:

- **In-code dataset**: a Python module defining `Case`/`Dataset` directly — the default for an agent-driven workflow.
- **Hosted/managed dataset**: cases live in the Logfire UI, edited by non-engineers, pulled/pushed via a separate `LogfireAPIClient` (`from logfire.experimental.api_client import LogfireAPIClient`). `client.get_dataset(name)` with no type arguments returns a raw dict, not something `push_dataset` or `.evaluate_sync()` can take — pass the input/output (and metadata, if used) types to get back a real `pydantic_evals.Dataset`: `client.get_dataset(name, MyInputType, MyOutputType)`. If the stored dataset contains custom evaluators, also pass their classes with `custom_evaluator_types=[ExactMatch]` (and custom report evaluators with `custom_report_evaluator_types=[...]`) so they can be deserialized. Push with `client.push_dataset(dataset)`. This needs its own API key from **Settings → API Keys** (scoped `project:read_datasets`/`project:write_datasets`), not Step 2's CLI auth flow. Only relevant if the user specifically wants case editing outside code.

## Step 4: Define the Dataset and Run It

```bash
uv add 'logfire[datasets]'
```

```python
from dataclasses import dataclass

import logfire
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance

logfire.configure()  # omit this and results stay local only, silently


@dataclass
class ExactMatch(Evaluator[str, str]):
    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        return ctx.output == ctx.expected_output


def classify_sentiment(text: str) -> str:
    ...  # the function under test


dataset = Dataset[str, str, None](
    name='sentiment-eval',
    cases=[
        Case(name='positive', inputs='I love this', expected_output='positive'),
        Case(name='negative', inputs='This is terrible', expected_output='negative'),
    ],
    evaluators=[ExactMatch(), IsInstance(type_name='str')],
)

report = dataset.evaluate_sync(classify_sentiment)  # or `await dataset.evaluate(...)`
report.print(include_input=True, include_output=True)
```

**Before running the full dataset, run a smoke test on 2-3 cases** if the dataset is large or uses `LLMJudge`/any evaluator that makes a real, billed model call — a bug caught on 3 cases costs 3 model calls, the same bug caught on 300 costs 300:

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

Confirm the smoke run has zero unexpected errors and the assertions that should pass do. Then, if the full dataset is large or uses paid model calls, tell the user the case count and which evaluators will make model calls, and get explicit confirmation before running the full dataset — don't run an expensive full pass on the strength of a clean smoke test alone without saying so.

Custom evaluators **must be `@dataclass`** subclasses — a plain class raises at run time. Case names must be unique within a dataset. The evaluators reached for most:

| Evaluator | Checks |
|-----------|--------|
| `Equals(value)` / `EqualsExpected()` | Exact match against a literal / `expected_output` (no-op if `expected_output` is unset — don't rely on it silently catching that) |
| `IsInstance(type_name)` | Output's type matches by name |
| `LLMJudge(rubric, model=None, score=False)` | LLM-as-judge scoring; costs a real model call per case per judge — prefer boolean/categorical rubrics over 1-10 scales (judges are unstable on continuous scores), and benchmark the judge against ~20-100 hand-labeled cases before trusting it |
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
