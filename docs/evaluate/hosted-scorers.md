---
title: "Score production traffic with hosted scorers"
description: "Have Logfire judge your recorded agent runs and spans on a schedule, with an AI judge or a SQL expression, and write a score for each one."
---

# Score production traffic with hosted scorers

Find out how good your agent's answers are in production without adding evaluator code to your application. A **hosted scorer** is a check that Logfire runs for you: on a schedule, it finds new records that match a filter you choose, judges each one, and writes the result back into your project next to the record it judged.

A scorer (the thing that judges an output and produces an evaluator result) can judge in two ways:

- **AI judge**: an **LLM-as-a-judge** (a language model that scores another model's output) reads the recorded run and applies judging instructions that you write, such as "Pass when the response answers the user's actual question." The model runs through your organization's [AI Gateway](../reference/advanced/gateway/index.md).
- **SQL check**: a SQL expression over the fields the record already contains, such as `NOT is_exception` or `duration < 10`. No model is called.

Each result is a pass/fail verdict, a number on a scale you set, or one of the category labels you define. This is **online evaluation** (scoring real production traffic as it happens, like monitoring), so results arrive continuously rather than in one experiment run.

!!! note "Early Access"
    Hosted scorers are in Early Access. To turn them on, open [**Settings → Early access**](https://logfire.pydantic.dev/settings/early-access) and enable **Hosted scorers** in the **AI Agent Optimization** section. Early-access choices apply to your account in this browser, so each teammate who wants to see the pages turns it on for themselves. Hosted scorers may change while in Early Access.

    Turning the option off only hides the pages. Scorers that already exist keep running, and AI judges keep using your AI Gateway. To stop scoring, pause or delete the scorer.

## When to use hosted scorers

Use a hosted scorer when you want a quality signal on traffic that already reaches Logfire and you don't want to change or redeploy your application to get it. Because it runs on recorded telemetry, it works for any service that sends data to Logfire, whatever language or framework produced it.

Use a different tool when:

- You want to test a change **before** you ship it against a fixed set of cases. Run an [offline evaluation](datasets-and-experiments.md) instead.
- You want an evaluator to run **inside your process**, for example with access to objects that never reach telemetry. Use [Pydantic AI online evaluation](https://pydantic.dev/docs/ai/evals/online-evaluation/), whose results also appear in [Live Evals](live-evals.md).

## Before you start

- **Permissions.** Anyone who can read the project can see scorers and their results. Creating, editing, testing, enabling, and deleting a scorer requires the **Change project info** project permission.
- **For an AI judge**, you also need:
    - the AI Gateway enabled for your organization, with at least one route (a provider connection that requests go through). See [AI Gateway](../reference/advanced/gateway/index.md).
    - **Enable AI features** turned on in your organization settings. Automatic AI scoring also needs **Proactive AI enabled**.
    - to be a project or organization admin with permission to use the AI Gateway. Only an admin can save, enable, or test an AI judge, because its model calls are paid from a project key rather than from a member's own budget (see [What it costs](#what-it-costs)).

A SQL check needs none of the AI requirements.

## Create a scorer

1. Open <OpenInLogfire path="scorers" variant="inline" label="Hosted scorers" /> under **AI Runtime** in the project sidebar, and select **Add scorer**. To score one agent, you can instead open the agent from the **Agents** page, select its **Scorers** tab, and select **Add scorer** there. The agent is then filled in for you.
2. Choose a starting point. Under **Start from scratch**, choose **AI judge** or **SQL check**. Under **Library**, choose a ready-made check, such as **Answers the request**, **Grounded in evidence**, or **Completed without an error**. A check from the library fills in the form, and you can edit everything before saving.
3. Under **What to score**, set **Find spans by** to **Agent name** and pick the agent, or to **SQL filter** and enter a `WHERE` condition on the `records` table, such as `service_name = 'support-api'`. A SQL filter can match any span or log, not only AI runs. When you start from an agent's **Scorers** tab, this step is already done.
4. Describe the judgment.
    - For an AI judge, write the **Judging instructions**. Say what a good run looks like, what fails, and when the judge should return not applicable.
    - For a SQL check, write the **SQL expression**. For **Pass / fail** it returns true or false, for **Numeric** a number within the range you set, and for **Category** one of your labels.
5. Pick the **Score type**: **Pass / fail**, **Numeric** (with **Minimum**, **Maximum**, and an optional **Passing threshold**), or **Category** (2 to 20 labels, each of which can be marked **Counts as passing**).
6. Enter a **Scorer name**. Logfire derives a **Result name** from it, which identifies the scores in the telemetry.
7. Open **Advanced settings** to adjust the remaining options (see [Choose the judge model](#choose-the-judge-model) and [Control what gets scored](#control-what-gets-scored)).
8. Select **Create scorer**.

By default, a new scorer starts scoring as soon as you save it. To save it paused instead, clear **Start scoring when saved** under **Advanced settings → Automatic scoring**.

!!! warning "An enabled AI judge spends money continuously"
    While automatic scoring is on, an AI judge sends recorded content from each scored record to the model behind your chosen gateway route, and every judgment is a paid model request. It continues until you pause or delete the scorer. Test the scorer and check its estimate before you save it with scoring on.

## Test a scorer before you save it

The editor lets you try the current form on real records without saving anything. A test writes no scorer and no score.

1. In **Test on a recorded span** (or **Test on a recorded run**, for an agent), choose **Last hour** or **Last 24 hours**, then select **Find matching spans** (or **Find matching runs**). The table lists up to 20 recent matches. Open a record's name to see it in the Live view in a new tab.
2. Select a record and select **Test scorer**. The result shows the verdict and the judge's explanation. For a SQL check you can select several records and test them together.
3. For an AI judge, select **Inspect judge input** to see exactly what the model would read. This does not call the model, so it costs nothing.
4. Under **Volume and cost**, select **Estimate**. It counts the matches from the last 24 hours and shows the judgments a day that the schedule would make and an **Estimated cost**. The info icon beside **Estimated cost** shows the breakdown.

Change the instructions or expression and test again until the verdicts match your own judgment of those records. Changing the judging settings clears the previous result but keeps your selected records.

Testing an AI judge calls the model through your gateway route, and is billed like any other gateway request. An AI judge tests one record at a time.

## Choose the judge model

For an AI judge, **Advanced settings → Judge** shows a **Gateway route** and a **Model**, chosen the same way as in the [Prompt Playground](../guides/web-ui/prompt-playground.md). When your organization has the built-in Anthropic route, the editor preselects it with a Claude Haiku model. You can choose any route and model your gateway allows.

You don't create or choose an API key. When an admin saves an AI judge, Logfire creates or reuses one managed gateway key for the project, and every AI judge in the project uses it. You can't view, edit, or revoke that key, but its spend appears as **Hosted scorers** in your gateway usage and cost views, and the gateway's [spending limits](../reference/advanced/gateway/spending-policies.md) apply to it.

**Judgments per record** can be 1, 3, or 5. More than one judgment of the same record shows how often the judge agrees with itself, at that many times the cost.

### Where the judge's input goes

The judge's input contains recorded content from your telemetry, such as the user's request, the agent's response, and tool results. Logfire sends it to the provider behind the route you choose, so that provider's data handling terms apply. If you need specific terms, for example zero data retention, configure a route to a provider that offers them and choose that route.

### What the judge reads

**Context scope** decides how much the judge sees: **Selected record** (the scored span or log on its own) or **Surrounding trace** (also the related spans in the same trace, such as tool calls). Clear **Include recorded inputs** to judge only the selected record's AI response.

The judge's input has a size budget, about 16,000 tokens (a token is the unit models read and bill by, a few characters of text). When the input is larger, Logfire shortens it to fit. It shortens the agent's instructions and long tool calls and results, and reduces the surrounding trace to a one-line outline per record. It keeps the final answer, the user's request, and error information, and shortens those only as a last resort. **Inspect judge input** marks a shortened input with a **Condensed** badge, shows the estimated size of the full input, and puts a marker at each cut. If the judge needs a detail that was cut, set **Context scope** to **Selected record**.

## Control what gets scored

**Advanced settings → Automatic scoring** sets how much traffic the scorer judges:

| Setting | What it does | Default |
| --- | --- | --- |
| **Share of runs judged** | The percentage of matching records to judge. Lower it to reduce cost on a busy target. | 100% |
| **Most runs judged per pass** | The most records one pass judges, from 1 to 500. Logfire judges several records of a pass at the same time. | 20 |
| **Run every** | How often a pass looks for new records: 1 minute, 5 minutes, 15 minutes, or 1 hour. | 1 minute |
| **Look back** | How far back each pass looks for records it has not judged yet. | 1 minute |
| **Environments** | Which deployment environments to score. Empty means every environment. | All |

When more records match in one pass than this setting allows, the pass judges up to the setting and then reports that it stopped early (see [Troubleshooting](#troubleshooting)). Lower **Share of runs judged**, narrow the filter, or raise the setting.

A project can have at most 100 hosted scorers.

## Turn scoring on and off

A scorer's page has two tabs: **Results** and **Configuration**. On **Configuration**, the **Automatic scoring** panel shows **Enabled** or **Paused**. Select **Enable scoring** to start it. The confirmation shows the schedule, the share of records, and, for an AI judge, that recorded context will be sent to the model. Select **Pause scoring** to stop it. A judgment that is already in progress can still finish.

### When Logfire pauses scoring

Logfire staff can pause hosted scoring for one organization or for a whole region, for example during an incident. The scorer pages then show a **Hosted scoring is paused by Logfire** notice, and a scorer that is switched on shows **Paused by Logfire**. While the pause lasts:

- Scorers do not judge new records, and tests that use an AI judge are turned off.
- Your scorers and the scores they already wrote are kept. You can still edit a scorer and test a SQL check.
- A scorer that you create is saved with scoring off.

When the pause ends, scorers that are switched on start again automatically. They catch up on about the last hour of records, so records from a longer pause stay unscored. A scorer that you created during the pause does not start by itself: select **Enable scoring**.

### Edit and delete

**Edit scorer** opens the saved settings. When you change how results are judged (the instructions or expression, score type, context, model, judgments per record, or result name), Logfire saves a new **judging version**. Use the **Judging version** picker on the **Configuration** tab to see the settings that produced older results. Renaming a scorer, or changing its target or schedule, doesn't create a new version.

**Delete scorer** removes the scorer. Scores it already wrote stay in your project as telemetry.

## Find your scores

Results appear in several places:

- **The scorer's Results tab** shows the pass rate, average, or label counts, and a table of results with each **Explanation**. Filter by environment and **Scoring version**, and use **View scored record** to open the record that was judged. **Open in Live view** shows the same results as raw records.
- **The Hosted scorers list** shows each scorer's target, whether automatic scoring is on, and a summary of its recent results.
- **[Live Evals](live-evals.md)** lists hosted results next to the online evaluations your own code reports. The target is the scorer's agent, or the scorer's name when it uses a SQL filter.
- **The Live view and trace view** show each result as a log under the record it judged. Its row shows the verdict, and the target icon opens the scorer that produced it.

### Query scores with SQL

Each result is an OpenTelemetry [`gen_ai.evaluation.result`](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md#event-gen_aievaluationresult) log event, stored like any other record, so you can query, chart, and alert on it. The useful attributes are:

| Attribute | Contains |
| --- | --- |
| `gen_ai.evaluation.name` | The scorer's **Result name** |
| `gen_ai.evaluation.score.label` | `pass`, `fail`, `not_applicable`, or a category label |
| `gen_ai.evaluation.score.value` | The number: `1` or `0` for pass/fail, the score for numeric scorers |
| `gen_ai.evaluation.explanation` | The judge's explanation |
| `gen_ai.evaluation.evaluator.version` | The judging version |
| `gen_ai.evaluation.id` | A unique ID for the result |
| `logfire.scorer.id` and `logfire.scorer.name` | The scorer that wrote the result |
| `logfire.scorer.score_type` | `pass_fail`, `numeric`, or `categorical` |

The result's `trace_id` and `parent_span_id` point to the record it judged.

This query, run in [Explore](../guides/web-ui/explore.md), lists recent failures with their explanations:

```sql
SELECT
  start_timestamp,
  attributes->>'logfire.scorer.name' AS scorer,
  attributes->>'gen_ai.evaluation.explanation' AS explanation,
  trace_id,
  parent_span_id AS scored_span_id
FROM records
WHERE span_name = 'gen_ai.evaluation.result'
  AND kind = 'log'
  AND attributes->>'logfire.scorer.id' IS NOT NULL
  AND attributes->>'gen_ai.evaluation.score.label' = 'fail'
ORDER BY start_timestamp DESC
LIMIT 50
```

This [dashboard](../guides/web-ui/dashboards.md) time series charts each pass/fail scorer's pass rate. Not-applicable results have no value, so `AVG` leaves them out:

```sql
SELECT
  time_bucket($resolution, start_timestamp) AS x,
  attributes->>'logfire.scorer.name' AS scorer,
  AVG(json_get_float(attributes, 'gen_ai.evaluation.score.value')) AS pass_rate
FROM records
WHERE span_name = 'gen_ai.evaluation.result'
  AND kind = 'log'
  AND attributes->>'logfire.scorer.score_type' = 'pass_fail'
GROUP BY x, scorer
ORDER BY x
```

To be notified when quality drops, use a query like this in an [alert](../guides/web-ui/alerts.md). In rare cases, a retried delivery writes the same result twice. Both copies share the same `gen_ai.evaluation.id`, so count distinct IDs when you need exact numbers.

## What it costs

A hosted scorer can have two costs:

- **AI inference** (AI judges only): every judgment is a normal AI Gateway request on the route you chose, billed and limited like any other gateway spend. It appears under **Hosted scorers** in your gateway usage.
- **Hosted-score fee**: a fee for each score that an AI judge or a SQL check writes, with 10,000 scores included in each billing cycle. The price depends on your plan. During Early Access, Logfire does not charge it.

The **Estimate** in the editor shows both parts for your current settings, including the fee for your plan, and is the place to check current numbers. A SQL check makes no model calls, so it has no inference cost.

### Set a daily budget for AI judges

Each project has a daily budget for the AI judge spend of its hosted scorers. On Logfire Cloud it starts at $50 a day. When the day's spend goes over the budget, the gateway refuses further judge requests until 00:00 UTC, and the affected scorers show **Scoring needs attention**. Requests that are already in progress still finish, so the spend can end slightly above the budget.

To change it, a project or organization admin who can use the AI Gateway opens the **Hosted scorers** page and selects **Daily budget**. The dialog shows today's spend. Enter a new amount under **Budget in US dollars a day**, or clear **Limit daily spend** to remove the budget. A change applies to the next judge request.

The budget covers AI inference only, and it is separate from your organization and project [spending limits](../reference/advanced/gateway/spending-policies.md), which also apply. When one scorer's maximum daily cost is above the budget, the **Estimate** shows a warning before you save.

## Manage scorers from a coding agent

The [Logfire MCP server](../how-to-guides/mcp-server.md) includes tools to manage hosted scorers, so a coding agent such as Claude Code can set up scorers for you:

| Tool | What it does |
| --- | --- |
| `scorer_list` | List the project's scorers. |
| `scorer_get` | Get one scorer's configuration. |
| `scorer_apply` | Create or update several scorers in one call. |
| `scorer_update` | Change existing scorers, including renaming a result or changing a target. |
| `scorer_delete` | Delete scorers. |

`scorer_apply` is declarative. It identifies a scorer by its target and result name, creates the scorer if it doesn't exist, and otherwise replaces its whole configuration, so a field you leave out returns to its default. One declaration can list several agents to create one scorer for each. A call writes at most 50 scorers, and it is atomic: if one item is invalid, nothing is saved, and the error names the item. Pass `validate_only` to check a call without saving it.

The reading tools need an API key with `project:read`, and the writing tools need `project:write`. Saving an AI judge through MCP has the same admin and gateway requirements as in the UI, and the key also needs the `project:gateway_proxy` scope.

## Verify it worked

After you save a scorer with scoring on, wait for new matching records to arrive and for the next pass to run (one minute with the default schedule). Then:

1. Open the scorer. The **Results** tab shows a count of results and a pass rate, average, or label counts.
2. Select **View scored record** on one result. The Live view opens the judged record, with the result as a child log that shows the verdict.

If nothing appears, check that **Automatic scoring** shows **Enabled** and not **Paused by Logfire**, that the filter matches recent records (use **Find matching spans** in the editor), and that the selected time range and environment include them.

## Troubleshooting

When automatic scoring fails, the scorer's page shows **Scoring needs attention** with one of these messages:

| Message | What to do |
| --- | --- |
| Your AI Gateway is disabled. Ask an organization admin to enable it. | An organization admin must [enable the AI Gateway](../reference/advanced/gateway/index.md#enable-the-gateway). |
| Spending limit reached: the hosted scorer daily budget, or a project or organization AI Gateway limit. ... | Wait for the daily limits to reset at 00:00 UTC, or raise the [daily budget](#set-a-daily-budget-for-ai-judges) on the **Hosted scorers** page or the [spending limit](../reference/advanced/gateway/spending-policies.md) in the AI Gateway settings. |
| Gateway spending limit reached. Check your organization, project and provider spending settings. ... | A spending policy blocked the request, or the gateway has no credit left. Raise the [spending limit](../reference/advanced/gateway/spending-policies.md) or add credit. Scoring resumes after that. |
| This scorer is not connected to your AI Gateway yet. A project admin needs to save it to connect it. | A project or organization admin opens the scorer, selects **Edit scorer**, and saves it. This creates the project's managed gateway key. |
| Your AI Gateway rejected the hosted scorer credentials. Check the provider credentials, then ask a project admin to save the scorer. | Fix the provider credentials on the gateway route, then have an admin save the scorer again. |
| Model blocked by your gateway. Check the route, allowed models and provider credentials. | Allow the model on the route, or choose another model and save. |
| The selected gateway model is unavailable. Choose a route and model in the scorer settings, then save the scorer. | The route was removed or the model is unavailable. Choose another and save. |
| Scoring stopped before all matching records could be evaluated. ... | Narrow the filter or shorten **Look back**. |
| The SQL expression returned an invalid score. ... | Make the expression return the type the score type expects, and test it on a record. |

If you can't enable an AI judge, the scorer page says why. **AI features are disabled for this organization** and **Proactive AI is disabled for this organization** both mean an organization admin must turn on the matching option in the organization settings.

## Next steps

- [Monitor all your online evaluation results in Live Evals](live-evals.md).
- [Build a dataset from runs that failed](datasets-and-experiments.md), so you can test a fix before you ship it.
- [Learn how evaluations fit together](overview.md).
