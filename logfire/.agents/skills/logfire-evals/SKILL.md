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

Skip this if `.logfire` credentials or `LOGFIRE_TOKEN` already resolve to the right project and region (check with `logfire whoami` first). Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency:

```bash
logfire auth
logfire projects list
logfire projects use <project-name>
logfire whoami
```

- Determine the target region (US or EU) from the project's URL or the user's context *before* authenticating. The `--region` flag is global and goes right after `logfire`, not after the subcommand: `logfire --region eu auth`. Omit it and let `auth` ask if the region is unknown — it completes without a TTY either way.
- `auth` opens a browser to sign in or create a free account.
- `projects list`: if exactly one project is available, use it. Several plausible and none identified? Ask. None exist? `logfire projects new <project-name>` instead. Need a specific org? Add `--org <organization-name>` to `projects use`.
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

A report printing to the terminal isn't proof it reached Logfire — confirm the run actually landed:

1. **Open AI Evaluations → Datasets & Experiments → Experiments** in Logfire for the exact project from Step 2, and find the run by name/timestamp.
2. **Read the Overview tab** first: completion count, assertion pass mix, task errors, average duration. **If completion says "Not reported,"** the run sent case data but never signaled it finished — treat that as a broken run, not a passing one.
3. **Open the Cases tab**, starting from Needs Review / Failed / Errors, not the full list.
4. **Drill into a failing case's trace in Live view** for the actual evidence, rather than trusting the summary score alone.
5. **Fix and re-run** until the cases that should pass do, and any tool-call/trajectory checks show real span data, not "No span tree available."
