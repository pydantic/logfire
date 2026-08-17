---
title: "Move from Braintrust to Logfire"
description: "Send an existing Braintrust evaluation suite to Logfire, then migrate datasets, evaluators, prompts, and production scoring at your own pace."
---

# Move from Braintrust to Logfire

Keep your existing Braintrust `Eval` code and send its next completed evaluation to Logfire by changing two environment variables. You can then replace Braintrust concepts with native Logfire and Pydantic Evals workflows one at a time.

!!! note "Compatibility preview"

    Logfire has verified the normal `Eval` flow from the Python `braintrust` 0.30.1 and TypeScript `braintrust` 3.24.0 packages. The compatibility endpoint does not implement the complete Braintrust API. Start with a staging or continuous integration (CI) run and check the [supported workflow](#know-what-the-compatible-endpoint-covers) before moving production evaluation jobs.

## Send your next evaluation to Logfire

You need a Logfire project and its **write token**, the credential that selects the destination project and lets the Braintrust SDK send evaluation data. Copy one from **Project → Settings → Write tokens** in Logfire.

Set the Braintrust app URL to the compatibility endpoint for your Logfire data region. Put the write token in the variable where the Braintrust SDK expects its API key:

```bash
# US project
export BRAINTRUST_APP_URL="https://logfire-us.pydantic.dev/v1/braintrust"
export BRAINTRUST_API_KEY="<your-logfire-write-token>"

# Remove overrides that would send part of the run somewhere else.
unset BRAINTRUST_API_URL
unset BRAINTRUST_PROXY_URL
```

For an EU project, use `https://logfire-eu.pydantic.dev/v1/braintrust` instead. Keep the token out of source control.

Run the same Python or TypeScript evaluation command you use today. The compatibility endpoint makes no request to Braintrust. It accepts the SDK protocol, translates the completed run into Logfire experiment data, and returns a result link that opens Logfire.

This change affects future runs only. It does not import Braintrust history, copy hosted resources, or send the run to both services.

## Verify the first run

Let the SDK finish its normal score summary, then use either route:

1. Open the result URL printed by the Braintrust SDK.
2. Or open the destination Logfire project, select **Experiments** in the sidebar, and open the newest run.

Confirm that the experiment contains the expected cases and evaluator results. Case data appears when the SDK requests its final comparison summary, so it does not appear incrementally while the run is still in progress.

One naming difference matters immediately: the write token selects the actual Logfire project. The string passed as the first argument to `Eval(...)`, which Braintrust calls a project, becomes the dataset name used to group experiments inside that Logfire project.

## Translate evaluation concepts

The two systems use similar evaluation shapes, but some nouns have different boundaries.

| If you know this in Braintrust | Use this in Logfire | What changes |
| --- | --- | --- |
| Organization | Organization | The team and access-control boundary remains an organization. |
| Project | Logfire project | A Logfire project holds the telemetry, datasets, experiments, prompts, and other resources for an application or environment. With the compatibility endpoint, the write token selects this project. |
| `Eval("support", ...)` project argument | Dataset name `support` | The compatibility endpoint uses Braintrust's project argument to group related experiments as a Logfire dataset. In native Pydantic Evals, set [`Dataset.name`](../evaluate/evals-in-code.md) directly. |
| Dataset | Code-defined or hosted dataset | Keep cases beside your code in a `pydantic_evals.Dataset`, or [manage a hosted dataset](../evaluate/manage-datasets.md) with your team in Logfire. Braintrust-hosted datasets do not pass through the compatibility endpoint. |
| Dataset row `input` | `Case.inputs` | Both hold the value passed to the task. |
| Dataset row `expected` | `Case.expected_output` | Both hold the value an evaluator can compare with the task output. |
| Task | Evaluation task | Pass the function or agent under test to `Dataset.evaluate()` or `evaluate_sync()`. |
| Scorer | Evaluator | A Pydantic Evals evaluator can return a pass/fail assertion, a numeric score, or a categorical label. See [Evals in code](../evaluate/evals-in-code.md). |
| Classifier | Evaluator that returns a label | The compatibility endpoint maps one classification per name to a Logfire label. It retains additional source data, but it cannot represent several classifications with the same name as one native label. |
| Experiment | Experiment | Each completed run records its cases, outputs, evaluator results, duration, and traces for review. Token use and cost appear when the task reports them. |
| Baseline and experiment comparison | Compare experiment runs | [Review experiments](../evaluate/review-experiments.md) to choose a baseline and inspect improvements, regressions, errors, and coverage changes. The compatibility endpoint supports explicit IDs and named baselines; its automatic choice is the newest prior run, not Braintrust's Git-branch-aware selection. |
| Experiment trace and child spans | Experiment case trace | Open a case trace to see the task, model calls, tools, database work, and other operations behind the result. |

If your current suite passes inline data, tasks, and scorers to `Eval`, you can keep those objects while you test Logfire. Moving to Pydantic Evals later removes the compatibility layer and gives you native typed cases and evaluator results.

## Translate the surrounding workflow

These are workflow replacements, not protocol translations. The Braintrust compatibility endpoint does not move the resources in this table for you.

| Braintrust workflow | Logfire workflow | Migration note |
| --- | --- | --- |
| Logs, traces, and spans | [Live View](../guides/web-ui/live.md) and [Agents](../guides/web-ui/agents.md) | Send application telemetry to Logfire with a native SDK or OpenTelemetry. Evaluation traces then sit beside the production services they exercised. |
| Online scoring | [Pydantic AI online evaluation](https://pydantic.dev/docs/ai/evals/online-evaluation/) and [Live Evaluations](../evaluate/live-evals.md) | Define online evaluators in application code. Braintrust server-side scoring rules are not executed by the compatibility endpoint. |
| Feedback and human review | [Run annotations and annotation queues](../evaluate/human-review.md) | Use Logfire's native review workflow for new judgments. Feedback comments logged through the Braintrust SDK before experiment finalization are retained, but feedback added after finalization is not applied. |
| Hosted prompts | [Prompt Management](../reference/advanced/prompt-management/index.md) | Re-create and test prompt templates in Logfire. The compatibility endpoint does not fetch Braintrust prompts or translate their template syntax. |
| Playground | [Prompt Playground](../guides/web-ui/prompt-playground.md) or [Prompt Management test scenarios](../reference/advanced/prompt-management/scenarios.md) | Use Prompt Playground to rerun a captured agent interaction. Use Prompt Management when the prompt is a versioned runtime resource. |
| Model proxy | [Logfire AI Gateway](../reference/advanced/gateway/index.md) | Configure the model SDK separately. `/v1/braintrust` is an evaluation compatibility endpoint, not a model proxy. |
| BTQL and saved data views | [PostgreSQL-compatible SQL](../reference/sql.md) | Query evaluation and application telemetry together, then save useful queries as dashboards or alerts. |
| Loop | [Logfire MCP server](../how-to-guides/mcp-server.md) | Ask a coding agent to query experiments and traces through Logfire's SQL surface. This is the closest investigation workflow, not a direct import of Loop sessions or actions. |
| Hosted functions, workflows, and remote parameters | Application code, Pydantic AI, and [Managed Variables](../reference/advanced/managed-variables/index.md) | Keep tools, workflows, and evaluators in your application. Use Managed Variables for runtime configuration. Logfire does not translate Braintrust-hosted functions. |

## Choose how far to migrate

You do not need to rewrite the suite before evaluating Logfire:

1. **Redirect one verified eval job.** Change the endpoint and key, then compare the resulting cases, scores, traces, and query workflow.
2. **Move the source of test cases if needed.** Inline and callable data already work. For Braintrust-hosted datasets, export the cases and create a [hosted Logfire dataset](../evaluate/datasets-sdk.md) or put them in a code-defined `pydantic_evals.Dataset`.
3. **Adopt native evaluators when they improve the code.** Replace Braintrust scorers with Pydantic Evals evaluators gradually instead of translating the whole suite at once.
4. **Replace hosted workflows explicitly.** Move prompts, online scoring, model routing, and runtime configuration to their native Logfire equivalents only after testing each one.

## Know what the compatible endpoint covers

The verified Python and TypeScript flows support inline or callable data, local tasks and scorers, structured inputs and outputs, multiple numeric scores, one categorical result per name, metadata, tags, trials, concurrency, task and scorer child spans, and normal summary finalization.

The endpoint does not provide Braintrust-hosted datasets, prompts, functions, remote parameters, attachments, object-storage overflow, arbitrary BTQL, the model proxy, server-side scoring, public sharing, or post-finalization feedback mutation. It also does not project Rust `Eval`, manual `flush()` without comparison, or runs with `summarize_scores=False` because those flows do not request the summary that finalizes the experiment.

## Troubleshoot the switch

**The SDK still contacts Braintrust:** Unset `BRAINTRUST_API_URL` and `BRAINTRUST_PROXY_URL`. Those overrides take precedence over the URLs returned by compatibility login.

**The endpoint returns `401`:** Confirm that `BRAINTRUST_API_KEY` contains a Logfire project write token, not a Logfire user token or a Braintrust API key. Confirm that the endpoint region matches the project.

**The experiment exists but has no cases:** Let the normal SDK summary finish. Do not set `summarize_scores=False`, rely on manual `flush()`, or use the Rust SDK for this compatibility path.

**A hosted resource returns `501`:** The message identifies a Braintrust cloud resource that the compatibility endpoint does not implement. Move that resource using the matching native workflow above rather than retrying the request.

## Next steps

- [Run a native evaluation](../evaluate/evals-in-code.md) when you are ready to replace the compatibility layer.
- [Review experiments](../evaluate/review-experiments.md) to compare the first Logfire run with its next iteration.
- [Compare Logfire and Braintrust](https://pydantic.dev/logfire/vs-braintrust) for the broader product differences.
