---
name: logfire-evals
description: Evaluate Python AI/agent code against a dataset of test cases using pydantic_evals, and review results in Logfire's Datasets & Experiments UI. Use this skill whenever the user asks to "set up evals", "add an evaluation", "test my agent against cases", "write a dataset of test cases", "score my LLM output", "add an LLM judge", "check tool-call correctness", or mentions pydantic_evals, Datasets & Experiments, or evaluating AI/agent behavior against known inputs. This is Python-only, and is for scoring DEFINED test cases offline — not for instrumenting live production traffic (use `logfire-instrumentation` for that) and not for infrastructure monitoring (use `logfire-infrastructure`).
---

# Evaluate with pydantic_evals and Logfire

## When to Use This Skill

Invoke this skill when:
- User wants to test or score an agent/function against a set of known inputs and expected outputs
- User asks to "add evals", "write test cases for my agent", "score outputs with an LLM judge"
- User wants tool-call correctness checked — did the agent call the right tools, in the right order, with the right arguments
- User mentions `pydantic_evals`, `Dataset`, `Case`, `Evaluator`, or Logfire's Datasets & Experiments page

## How This Works

`pydantic_evals` runs your actual function or agent against a `Dataset` of `Case`s (input + expected output + metadata), scores each with one or more `Evaluator`s, and produces a report. It depends on `logfire` itself (the `datasets` extra pulls in the real SDK, not a mock), so whether `logfire.configure()` has run determines only whether results *also* upload to Logfire's Datasets & Experiments UI — omitting it keeps results entirely local and printed to the terminal, **silently, not an error**.

Agentic evaluators (tool-call correctness, trajectory matching) need more than that: they read the task's own execution span tree, so without a working `logfire.configure()` they don't just fail to upload — every case reports "No span tree available" and the check never ran at all.

## Step 1: Detect What to Evaluate

Identify the function or agent under test (a PydanticAI agent, an LLM-calling function, any callable that takes an input and returns an output) and whether a dataset already exists:

- **In-code dataset**: a Python module defining `Case`/`Dataset` directly — the default for an agent-driven workflow.
- **Hosted/managed dataset**: cases live in the Logfire UI, edited by non-engineers, pulled/pushed via a separate `LogfireAPIClient` (`from logfire.experimental.api_client import LogfireAPIClient`) — `client.get_dataset(name, include_cases=True)` / `client.push_dataset(dataset)`. This needs its own API key from **Settings → API Keys** (scoped `project:read_datasets`/`project:write_datasets`), not the CLI auth flow below. Only relevant if the user specifically wants case editing outside code.

## Step 2: Authenticate and Select the Exact Project

Check first, before assuming anything needs to happen:

```bash
logfire --non-interactive whoami
```

If that already reports the right project and region, skip to Step 3. Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency. **Always put `--non-interactive` immediately after `logfire`, on every invocation.** Without it, a question with nobody to answer it (which org? which project?) blocks on a read that never returns — there is no TTY for the CLI to notice is missing, so it cannot detect this on its own; the flag is the only way to guarantee a clear error instead of a silent hang.

```bash
logfire --non-interactive --region eu auth
logfire --non-interactive projects list --json
logfire --non-interactive projects use <project-name> --org <organization-name>
logfire --non-interactive whoami
```

- Determine the target region (US or EU) from the project's URL or the user's context *before* authenticating, and pass it up front: `--region {us,eu}` is global and goes right after `logfire --non-interactive`, before the subcommand.
- `auth` does **not** open a browser itself when there's no TTY, which an agent's own environment never has — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently.
- `projects list --json`: if exactly one project is returned, use it. Several plausible and none identified? Ask the user. None exist? `logfire --non-interactive projects new <project-name> --org <organization-name>` instead.
- If any command fails with `NonInteractiveError`, its message names the exact missing flag (commonly `--org`). Supply it and retry once — don't drop `--non-interactive` to make the error go away.
- Never print, log, hard-code, commit, echo, or read a token or its credentials file — check only whether it exists, not its contents. This flow is only for `logfire.configure()`; hosted-dataset operations use a separate API key (Step 1) with different scopes.

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
