---
title: "Discover a material-response equation with an agent"
description: "Search over executable hypotheses with an agent, run them in Logfire Agent Sandboxes, and independently measure their quality."
---

# Discover a material-response equation with an agent

**An agent searches over executable hypotheses, while the application independently measures their quality.**

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

In this example, a hypothesis is a Python function that predicts a material's stress from its strain.
Stress measures the force applied per unit area. Strain measures the relative change in length.
The agent uses synthetic observations to propose an equation, fit its coefficients, and revise the equation's form.
Your application runs each submitted function and measures its prediction error against private observations.

The hypothesis is an executable artifact. To test it, you must run code that the model generated.
A plausible explanation is not evidence that the program works or that its predictions fit the data.
The feedback loop is concrete: **propose a program, execute it, measure its error, revise the hypothesis**.

[Agent Sandboxes by Logfire](index.md) provides the execution boundary this loop depends on.
It runs the agent's fitting experiments and replays submitted hypotheses in isolated Python sessions, with bounded
execution time and memory. Your application keeps credentials, private validation and final-test labels, and the
scoring calculation under its control. Logfire records the generated programs, tool calls, and results alongside the agent that requested them,
so you can inspect the experiment behind each score.

[Code Mode](pydantic-ai.md), a capability that turns an agent's tools into functions its Python scripts can call,
connects the agent to this loop. It lets the agent inspect residuals (differences between predictions and observations),
run short fitting loops, and submit complete candidate programs for evaluation.

## Before you start

- Use Python 3.11 or later.
- Follow [Run code from Python](python.md) to create a Logfire project and set `LOGFIRE_API_KEY`.
  The key needs permission to run code in Agent Sandboxes and send telemetry.
- Set `OPENAI_API_KEY` to a key from the [OpenAI API keys page](https://platform.openai.com/api-keys).
  The example uses `openai-responses:gpt-5.6`. You can select another supported model with `MATERIAL_MODEL`.
- Install the packages:

```bash
pip install 'logfire[agent-sandboxes]>=5.6.0' 'pydantic-ai>=2.71.0' 'pydantic-ai-harness[codemode]>=0.71.0'
```

!!! warning "This run uses hosted services"
    Model requests incur provider charges. Generated programs, tool arguments, and tool results pass through Logfire
    for sandbox execution, and tracing records this content in your project. Use the synthetic data below for this
    example. See [tracing and storage](limits.md#understand-tracing-and-storage) before substituting private data.

## Fit and test the equation

Save the following code as `material_discovery.py`.
It exposes two tools: `get_observations` returns training pairs, and `evaluate_candidate` tests a submitted Python function.

The application divides the observations into three disjoint sets:

- **Training:** pairs the agent can read and use to fit coefficients.
- **Validation:** private pairs whose scores select the best candidate. The agent receives errors, not labels.
- **Final test:** untouched pairs evaluated only after the agent stops and the application freezes the winner.
  This includes strains beyond the training range, so it also checks extrapolation: predicting outside the range used for fitting.

Errors are normalized root mean square error (**NRMSE**): the square root of the average squared prediction error,
divided by the training stress range. Lower is better; zero means an exact fit on the evaluated points.
All three sets use the same normalization.

```python title="material_discovery.py" skip-run="true" skip-reason="external-connection"
import asyncio
import math
import os

from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import CodeMode
from pydantic_monty import (
    MontyConversionError,
    MontyRuntimeError,
    MontySyntaxError,
    MontyTypingError,
)

import logfire

MAX_ATTEMPTS = 12
INSTRUCTIONS = """Discover a compact equation for stress as a function of strain.
Use run_code for all calculations. Every call starts a fresh sandbox: fetch observations
and include all imports and constants again. Use only Python and math, with no packages.
First fit a line through the origin using sum(x*y)/sum(x*x) and submit it.
Then inspect residuals, change the equation's shape, and fit its coefficients.
Use algebra or short search batches, at most 50 trial parameter sets per call.
Submit each plausible improvement; do not spend the whole budget without submitting.
Nested tools are async, so await them. Return compact summaries, not all the data.
Submit source as a string defining predict(strain: float) -> float, with all constants
and imports included. The application replays it in a separate, fresh sandbox.
Prefer an interpretable equation over a lookup table or interpolation of observations.
Training pairs are available; validation labels and final-test labels are private.
Stop when attempts_remaining is zero or improvements are negligible. Do not invent scores.
"""


def observations():
    # This generator runs on the host. It is not exposed as an agent tool.
    pairs = [(i / 1000, 20000 * (i / 1000) / (1 + 80 * (i / 1000))) for i in range(121)]
    return pairs[:81:3], pairs[1:81:3], pairs[2:81:3] + pairs[81:]


def error(predicted, rows, scale):
    return math.sqrt(sum((p - y) ** 2 for p, (_, y) in zip(predicted, rows)) / len(rows)) / scale


async def predict(pool, source, rows):
    if len(source.encode()) > 16000:
        raise ValueError('Source exceeds 16,000 bytes')
    limits = {'max_feed_duration_secs': 0.05, 'max_turn_duration_secs': 0.05, 'max_memory': 16 * 1024 * 1024}
    async with pool.checkout(limits=limits) as session:
        await session.feed_run(source + '\nNone', print_callback=lambda *args: None)
        values = await session.feed_run(
            '[predict(x) for x in strains]',
            inputs={'strains': [x for x, _ in rows]},
            print_callback=lambda *args: None,
        )
    if not isinstance(values, list) or len(values) != len(rows):
        raise ValueError('Return one scalar per strain')
    if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
        raise ValueError('Predictions must be finite numbers')
    return values


async def main():
    api_key = os.environ['LOGFIRE_API_KEY']
    logfire.configure(service_name='material-discovery-example', token=api_key, api_key=api_key)
    logfire.instrument_pydantic_ai()
    train, validation, test = observations()
    scale = max(y for _, y in train) - min(y for _, y in train)
    best = None
    attempts = 0
    hooks = Hooks()

    @hooks.on.before_tool_execute(tools=['run_code'])
    def restart_code(ctx, *, call, tool_def, args):
        return {**args, 'restart': True}

    async with logfire.agent_sandboxes(max_processes=1) as scoring_pool:

        async def get_observations() -> dict:
            """Return training [strain, stress] pairs, units, and the prediction domain."""
            return {'pairs': train, 'stress_unit': 'MPa', 'strain_unit': 'dimensionless', 'domain': [0, 0.12]}

        async def evaluate_candidate(source: str) -> dict:
            """Score standalone Python defining predict(strain); lower normalized error is better."""
            nonlocal attempts, best
            if attempts >= MAX_ATTEMPTS:
                return {'attempts_remaining': 0, 'error': 'Attempt budget exhausted'}
            attempts += 1
            try:
                values = await predict(scoring_pool, source, train + validation)
                train_error = error(values[: len(train)], train, scale)
                validation_error = error(values[len(train) :], validation, scale)
            except (
                ValueError,
                OverflowError,
                MontyRuntimeError,
                MontySyntaxError,
                MontyTypingError,
                MontyConversionError,
            ) as exc:
                return {'error': str(exc)[:200], 'attempts_remaining': MAX_ATTEMPTS - attempts}
            if best is None or validation_error < best['validation_error']:
                best = {'source': source, 'validation_error': validation_error}
            print(f'Attempt {attempts}: train={train_error:.3e}, validation={validation_error:.3e}')
            return {
                'train_error': train_error,
                'validation_error': validation_error,
                'best_validation_error': best['validation_error'],
                'attempts_remaining': MAX_ATTEMPTS - attempts,
            }

        agent = Agent(
            os.getenv('MATERIAL_MODEL', 'openai-responses:gpt-5.6'),
            name='material_discovery',
            instructions=INSTRUCTIONS,
            tools=[get_observations, evaluate_candidate],
            capabilities=[CodeMode(monty_sandbox=logfire.agent_sandboxes), hooks],
        )
        with logfire.span('discover material equation'):
            try:
                async with asyncio.timeout(120):
                    await agent.run(
                        'Fit and improve a stress-strain equation. Submit your candidates for scoring.',
                        usage_limits=UsageLimits(request_limit=10, tool_calls_limit=60),
                        model_settings={'max_tokens': 4000},
                    )
            except (UsageLimitExceeded, TimeoutError):
                print('Search budget reached; retaining the best completed candidate.')
            if best is None:
                raise RuntimeError('No valid candidate was submitted')
            # Freeze the winner before using the untouched test set. No more agent calls.
            test_error = error(await predict(scoring_pool, best['source'], test), test, scale)
            print('Best equation:\n' + best['source'])
            print(f'Best validation NRMSE: {best["validation_error"]:.3e}')
            print(f'Final-test NRMSE: {test_error:.3e}')


if __name__ == '__main__':
    asyncio.run(main())
```

Run it:

```bash
python material_discovery.py
```

The first candidate is a fitted line through the origin. Later candidates come from the agent's analysis of the data.
The application retains the lowest validation error even if a later candidate gets worse.
It allows 12 submissions, 10 model requests, and 120 seconds for the search. A request or time limit retains the best
completed candidate. A run with no valid candidate raises an error.

One run with `gpt-5.6`, routed through the AI Gateway, produced the following output. Logfire's console tracing lines
are omitted here. This is a recorded example, not a required sequence of candidates or a performance benchmark.

```text
Attempt 1: train=2.489e-01, validation=2.522e-01
Attempt 2: train=2.481e-16, validation=2.660e-16
Best equation:
def predict(strain: float) -> float:
    return (20000.00000000004 * strain) / (1.0 + 80.00000000000021 * strain)

Best validation NRMSE: 2.660e-16
Final-test NRMSE: 3.175e-16
```

Errors near `1e-16` are at the scale of floating-point rounding in this experiment. They show recovery of the synthetic
generator on these points, not measurement precision for a real material.

The observations and splits are fixed, but the agent's programs, candidate count, scores, and runtime vary between runs.
A low validation error alone does not establish extrapolation accuracy. Read the final-test error as well.

## See why the equation changes

The first hypothesis is `stress = a * strain`. The agent computes the best least-squares slope from the training data,
but its validation error is still about `0.252`. Adjusting the slope cannot remove the mismatch between a straight
line and the curved observations.

The next hypothesis changes the form to `stress = A * strain / (1 + B * strain)` and fits two coefficients.
The independently computed errors fall to the scale of floating-point rounding. The improvement comes from testing
a different equation structure, not from a more persuasive explanation or further tuning of the original slope.

If you already know the equation's form, a conventional numerical optimizer is usually a more direct way to fit its
coefficients. Methods such as symbolic regression can search equation structures too. This example demonstrates
an agent proposing and revising executable hypotheses; it does not establish superiority over those methods.

## Keep execution separate from measurement

Agent Sandboxes serves two roles in this experiment:

1. **Run the agent's experiments.** Code Mode executes fitting programs that can call `get_observations` and
   `evaluate_candidate`. These two functions run in your application and expose only the operations the agent needs.
2. **Replay each submitted hypothesis.** The scoring tool opens a separate fresh sandbox and runs the candidate's
   `predict` function with strain values. This session has no host functions, files, network access, or environment
   variables. The candidate must include its own imports and coefficients; it cannot depend on the fitting session's state.

Your application then compares the returned predictions with expected stress values and calculates the error.
It checks source length and rejects non-finite values and non-scalar results. It retains the lowest validation error
and freezes that candidate before calculating the final-test error. The agent cannot replace the scoring function
or choose which candidate the application declares best.

The sandbox enforces execution-time and memory limits on generated code. A fitting experiment or candidate can fail
without gaining access to application credentials or private validation and final-test labels. [Hosted resource policies](limits.md#resource-limits)
can impose additional limits. Generated code runs in the hosted interpreter; the application does not execute it
through host Python's `eval` or `exec`.

The hook sets Code Mode's public `restart=True` option on each `run_code` call.
Every fitting program starts a fresh sandbox and includes its own imports, observations, and constants.
The agent still sees earlier tool results in its conversation. Each program's execution appears under the tool call
that requested it in Logfire. Candidate scoring always uses a separate fresh session.

Agent Sandboxes supplies isolated, bounded, observable execution. Your application supplies independent measurement
and selection. Together, they let the agent explore new programs while keeping the experiment's rules outside those programs.
The generator appears in the example so you can inspect the experiment, but it is not one of the agent's tools.

## Verify it worked

1. Confirm the terminal prints a score for each valid candidate, then the retained equation and final-test error.
2. Open Logfire's [Live view](../guides/web-ui/live.md) and find `discover material equation`.
   A **trace** is the full journey of one request, made of nested **spans**: each span is one unit of work,
   a single operation with a name, a start, and a duration.
3. Expand the `material_discovery` agent invocation and a `run_code` tool call. Inspect the generated fitting program,
   its `get_observations` or `evaluate_candidate` calls, and the scoring sandbox's code runs inside the evaluation call.
   Compare the tool's returned errors with the printed scores.

`logfire.instrument_pydantic_ai()` records the native agent, model, and tool spans.
Agent Sandboxes adds its execution spans to the same trace.
The example passes the project API key explicitly for both telemetry and sandbox access, so an existing
`LOGFIRE_TOKEN` does not send its traces to a different project.

## Know the limits

The data is noiseless, one-dimensional, and synthetic. A low error on these points does not validate a physical law,
behavior under unloading, noisy measurements, or a real material.
The agent can also overfit validation scores after repeated submissions; keep the final test separate.

The executable-hypothesis loop gives you measured evidence about a program's predictions, not proof of a physical law.
It does not establish a speed or cost advantage over conventional fitting. If your fitting code requires third-party
packages inside the interpreter, check [what sandbox code can do](limits.md) before choosing this approach.

## Troubleshooting

- **The run fails with a missing API key or permission error:** check `LOGFIRE_API_KEY` against the permissions in
  [Run code from Python](python.md), and check the selected model's provider credentials. Authentication and service
  errors stop the run rather than count as evidence that an equation is bad.
- **A fitting loop exceeds the sandbox's resource limit:** reduce the number of trial parameter sets per call.
  Use shorter batches and submit a usable candidate before attempting a more expensive search.
- **A program fails because a variable is undefined:** each `run_code` starts fresh. Include imports, coefficients,
  and a call to `get_observations()` in the new program.
- **The agent reaches a budget limit or submits no valid candidate:** inspect its tool calls in the trace.
  Check that it submits standalone source defining `predict(strain)` and uses Python features supported by Monty.
  A completed valid candidate can be retained at a budget limit; no valid candidate means the run failed.

## Next steps

- [Inspect sandbox runs](inspect.md): read the code, results, and failures of individual executions.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): configure Code Mode and keep session state when you need it.
- [What sandbox code can do](limits.md): check supported Python features and resource limits before adapting the example.
