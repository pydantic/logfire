---
name: logfire-evals
description: Evaluate Python AI/agent code against a dataset of test cases using pydantic_evals, and review results in Logfire's Datasets & Experiments UI. Use this skill whenever the user asks to "set up evals", "add an evaluation", "test my agent against cases", "write a dataset of test cases", "score my LLM output", "add an LLM judge", "check tool-call correctness", or mentions pydantic_evals, Datasets & Experiments, or evaluating AI/agent behavior against known inputs. This is Python-only, and is for scoring DEFINED test cases offline — not for instrumenting live production traffic (use `logfire-instrumentation` for that) and not for infrastructure monitoring (use `logfire-infrastructure`).
---

# Evaluate with pydantic_evals and Logfire

## How This Works

`pydantic_evals` runs your actual function or agent against a `Dataset` of `Case`s (input + expected output + metadata), scores each with one or more `Evaluator`s, and produces a report. It depends on `logfire` itself (the `datasets` extra pulls in the real SDK, not a mock), so whether `logfire.configure()` has run determines only whether results *also* upload to Logfire's Datasets & Experiments UI — omitting it keeps results entirely local and printed to the terminal, **silently, not an error**.

Agentic evaluators (tool-call correctness, trajectory matching) need more than that: they read the task's own execution span tree, so without a working `logfire.configure()` they don't just fail to upload — every case reports "No span tree available" and the check never ran at all.

## Step 1: Detect What to Evaluate

Identify the function or agent under test (a PydanticAI agent, an LLM-calling function, any callable that takes an input and returns an output) and whether a dataset already exists:

- **In-code dataset**: a Python module defining `Case`/`Dataset` directly — the default for an agent-driven workflow.
- **Hosted/managed dataset**: cases live in the Logfire UI, edited by non-engineers, pulled/pushed via a separate `LogfireAPIClient` (`from logfire.experimental.api_client import LogfireAPIClient`) — `client.get_dataset(name, include_cases=True)` / `client.push_dataset(dataset)`. This needs its own API key from **Settings → API Keys** (scoped `project:read_datasets`/`project:write_datasets`), not the CLI auth flow below. Only relevant if the user specifically wants case editing outside code.

## Step 2: Authenticate and Select the Exact Project

Check first — `logfire --non-interactive whoami` — and skip to Step 3 if it already reports the right project and region. Otherwise, full command sequence, flags, and gotchas (the `--non-interactive` requirement, why `auth` won't open a browser for you, the `LOGFIRE_TOKEN`-vs-credentials-file conflict, token-file safety) plus where a hosted-dataset API key comes from: [Authenticate and Select the Exact Project](../logfire-instrumentation/references/auth.md). This CLI flow is only for `logfire.configure()`; Step 1's hosted-dataset operations use a separate API key with different scopes.

## Step 3: Define the Dataset and Run It

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
smoke = Dataset(name=dataset.name, cases=dataset.cases[:3], evaluators=dataset.evaluators)
smoke_report = smoke.evaluate_sync(classify_sentiment)
smoke_report.print(include_input=True, include_output=True)
```

Confirm the smoke run has zero unexpected errors and the assertions that should pass do. Then, if the full dataset is large or uses paid model calls, tell the user the case count and which evaluators will make model calls, and get explicit confirmation before running the full dataset — don't run an expensive full pass on the strength of a clean smoke test alone without saying so.

Custom evaluators **must be `@dataclass`** subclasses — a plain class raises at run time. Case names must be unique within a dataset. Built-in evaluators worth knowing:

| Evaluator | Checks |
|-----------|--------|
| `Equals(value)` / `EqualsExpected()` | Exact match against a literal / `expected_output` (no-op if `expected_output` is unset — don't rely on it silently catching that) |
| `Contains(value, ...)` | Substring / membership / dict-subset |
| `IsInstance(type_name)` | Output's type matches by name |
| `MaxDuration(seconds)` | Task finished within budget |
| `LLMJudge(rubric, model=None, score=False)` | LLM-as-judge scoring; costs a real model call per case per judge — prefer boolean/categorical rubrics over 1-10 scales (judges are unstable on continuous scores), and benchmark the judge against ~20-100 hand-labeled cases before trusting it |
| `ToolCorrectness(expected_tools, ...)` / `TrajectoryMatch(expected_trajectory, ...)` / `ArgumentCorrectness(tool_name, expected_arguments, ...)` | Which tools were called, in what order, with what arguments — reads the span tree, so needs Step 2's `logfire.configure()` to work at all, not just to upload |
| `MaxToolCalls(max_calls)` / `MaxModelRequests(max_requests)` | Budget ceilings on tool calls / LLM requests |

The `Python` evaluator (arbitrary code execution) was removed for security reasons — don't reach for it even if an older example references it.

If editing a hosted dataset: `client.push_dataset(dataset)` **overwrites** server-side evaluators on every push, including removing ones you deleted locally — don't push a stale local copy over a dataset others have edited in the UI.

## Step 4: Verify

A report printing to the terminal isn't proof it reached Logfire — confirm the run actually landed. **Never report a case as passed, a score, or a run as complete without having actually checked it in this session** — if a run fails, cancels, or produces no scores, report that failure plainly; never substitute an invented score or a manual guess at what the result "should" be.

1. **Query for the run directly, if a Logfire MCP server or API is connected** — the root span for a run is named `evaluate {name}` and carries `gen_ai.operation.name = 'experiment'`, `dataset_name`, and `task_name` attributes; find the most recent one matching your dataset's name and confirm `logfire.experiment.metadata` shows the case count and pass rate you expect. Otherwise, open **AI Evaluations → Datasets & Experiments → Experiments** in Logfire for the exact project from Step 2, and find the run by name/timestamp.
2. **Read the Overview tab (or the queried metadata) first**: completion count, assertion pass mix, task errors, average duration. **If completion says "Not reported,"** the run sent case data but never signaled it finished — treat that as a broken run, not a passing one.
3. **Open the Cases tab**, starting from Needs Review / Failed / Errors, not the full list.
4. **Drill into a failing case's trace in Live view** for the actual evidence, rather than trusting the summary score alone.
5. **Fix and re-run** until the cases that should pass do, and any tool-call/trajectory checks show real span data, not "No span tree available."

Close with a final report built from what you just confirmed — the run name, exact case count and pass rate you queried, and which evaluators ran — not a template.
