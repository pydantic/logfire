---
title: "Roll out a prompt safely"
description: "Take one prompt from a hardcoded string to a versioned, testable value you can promote to production and roll back in seconds, no redeploy."
---

# Roll out a prompt safely

You have an AI feature whose behavior lives in a prompt: the instruction text you send to a language model. Today, changing one line of that prompt is a code change: edit the string, open a pull request, wait for review, and redeploy the whole application before the new wording reaches users. When the change turns out worse, you do it all again in reverse.

This walkthrough takes a single prompt through the safe way to ship it: you'll move the prompt out of your source code, fetch it by a **label** (a movable pointer like `production`), save a new **version** of it, test that version before it goes live, **promote** it by moving the label (with no redeploy), and **roll it back** the same way if something looks off. At the end, shipping a prompt change is a label move measured in seconds, and every change is recorded.

**Who this is for:** an AI engineer who ships prompt changes and wants to stop coupling them to code deploys.

**Time:** about 15 minutes.

A few terms, defined once, so the steps read cleanly:

- A **prompt** is the instruction text you send to a language model: a system prompt, a template, or a reusable piece of one.
- A **version** is a saved snapshot of a prompt's text. Versions are numbered (v1, v2, v3, …) and never change once saved, so you always have a stable point to promote or roll back to.
- A **label** is a movable pointer such as `production` or `canary`. Your application fetches "whatever `production` points at" rather than a fixed version number, so promoting a change is just moving the label.

For the full model behind these terms, see [Prompt management concepts](../reference/advanced/prompt-management/concepts.md).

## Prerequisites

- **A Logfire project.** If you don't have one, create it in the Logfire web app.
- **A write token**, so your application can send **traces** (the recorded journey of each request, made of nested timed operations called **spans**). Create one in Logfire under **Project → Settings → Write tokens**, and set it in your application's environment as `LOGFIRE_TOKEN`.
- **An API key with the `project:read_variables` scope**, which is what lets your application *fetch* prompts (a write token can't). Create one under **Project → Settings → API keys**, and set it as `LOGFIRE_API_KEY`.
- **An API key for your language model provider**, from that provider's own dashboard. This walkthrough uses an OpenAI-style call, but the prompt-management workflow is the same for any provider.
- **The Logfire SDK with the variables extra**, which installs the prompt-fetching support:

  ```bash
  pip install 'logfire[variables]'
  ```

## 1. The starting point: a prompt hardcoded in your app

Here's the feature before prompt management, a support assistant whose system prompt is a Python string:

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

import logfire

logfire.configure()
logfire.instrument_openai()  # so each model call shows up as a trace in Logfire

client = OpenAI()

SUPPORT_PROMPT = """You are a support agent for Acme.
Be concise and friendly. If the customer asks for a refund,
explain the 30-day policy and offer to escalate."""


def answer(question: str) -> str:
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {'role': 'system', 'content': SUPPORT_PROMPT},
            {'role': 'user', 'content': question},
        ],
    )
    return response.choices[0].message.content
```

Every word of `SUPPORT_PROMPT` is frozen into the deployed code. To change the refund wording, you edit this file, get it reviewed, and redeploy. Let's take that string out of the code.

## 2. Author the prompt in Logfire and pull it in by label

First, create the prompt in Logfire so it lives outside your source tree:

1. In the Logfire web app, open the **Prompts** page and create a prompt named **Support Agent**.
2. Paste your instruction text as its first draft and save it as **v1**.
3. Move the `production` label to v1, so `production` now points at the text you just saved.

Now fetch it from your application instead of hardcoding it. Each prompt is exposed to your code under a name derived from its slug (the lowercase, hyphenated identifier in the prompt's URL): a prompt with slug `support-agent` is fetched as `prompt__support_agent`.

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

import logfire

logfire.configure()
logfire.instrument_openai()

client = OpenAI()

# Fetch the prompt Logfire is serving under the `production` label, instead of a
# hardcoded string. The `default` is a known-good fallback used only if the prompt
# can't be resolved (server unreachable, label missing), never an empty prompt.
prompt_var = logfire.var(
    name='prompt__support_agent',
    type=str,
    default=(
        'You are a support agent for Acme. Be concise and friendly. If the customer '
        'asks for a refund, explain the 30-day policy and offer to escalate.'
    ),
)


def answer(question: str) -> str:
    # Make the model call inside the `with` block so its span records which prompt
    # label and version produced the response (that's what makes step 4's audit work).
    with prompt_var.get(label='production') as resolved:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': resolved.value},
                {'role': 'user', 'content': question},
            ],
        )
    return response.choices[0].message.content
```

**What you'll see in Logfire:** your model calls still show up as traces, but now each request is tied to the prompt label and version that produced it, so you can tell later which wording a given response came from.

If your prompt has runtime placeholders (a customer name, a topic) written as `{{...}}`, use `logfire.template_var(...)` instead, which renders those placeholders for you. See [Use prompts in your application](../reference/advanced/prompt-management/application.md) for that variant.

## 3. Make a change: save a new version, then test it before it goes live

Your app is now serving v1 from the `production` label. When you want to change the refund wording, you don't touch the code at all:

1. On the **Prompts** page, open **Support Agent** and edit the draft, say, clearer escalation instructions.
2. Save it as **v2**. Saving a version and putting it live are separate steps: v2 exists now, but `production` still points at v1, so your running app is unaffected.

Before you promote v2, test it. You have two ways, depending on how thorough you want to be:

- **Quick check in the editor.** On the Prompts page, run v2 against saved test cases (Logfire calls these **scenarios**: saved inputs like a representative customer message). This renders the prompt and calls the model so you can read the output. To sweep v2 across many representative cases at once, link a scenario to a dataset for a batch run. See [Test prompts](../reference/advanced/prompt-management/ui.md#scenarios-panel).

  !!! warning "This spends real model budget"
      Running a prompt against the model calls your provider and costs money, and a batch run calls it once per case. Check the case count and model before running a large batch.

- **Score it with evaluations.** If you want a measured pass/fail rather than an eyeball check (for example, "did the answer mention the 30-day policy?"), run v2 through an evaluation: a dataset of representative inputs scored by a rule or an LLM-as-a-judge. This is how you catch a regression before users see it. See [Evaluate your AI](../evaluate/overview.md) for the full workflow.

## 4. Promote: move the `production` label to v2, no redeploy

Once v2 tests well, put it live by moving the label. Your prompt is backed by a managed variable named `prompt__support_agent` (the same object you fetch in code), and promotion happens there, not in your code:

1. In Logfire, open **Managed Variables** and open `prompt__support_agent`.
2. On the **Values** tab, move the `production` label from v1 to v2.
3. Save the label change.

Your running application fetches `prompt__support_agent` with `label='production'` and picks up v2 on its next resolution. **No redeploy, no code change, no pull request.** The switch is live in seconds.

**What you'll see in Logfire:** new traces now carry v2's label and version, while older traces still show v1, so you can compare response quality, escalation rate, latency, and token cost before and after the switch. See [Promote and roll out prompts](../reference/advanced/prompt-management/promotion-and-rollouts.md).

## 5. Roll back: move the label back (instant, no deploy)

Say v2 looks worse in production. Rolling back is the same move in reverse:

1. Open `prompt__support_agent` under **Managed Variables**.
2. Move the `production` label back to v1.
3. Save.

The next prompt resolution serves v1 again. Because v1 was never deleted (versions are immutable snapshots), you're back to the known-good text instantly, with no deploy. Your traces still record exactly which version was active for each request through the incident, so you can see what happened.

## 6. Optional: roll out to a percentage of traffic first

When you'd rather not flip 100% of traffic to a new version at once, send it to a slice first. Put v2 on a `canary` label, keep `production` on v1, and split traffic between them: for example 10% to `canary`, 90% to `production`. To make this work, fetch the prompt with a stable `targeting_key` (such as a tenant or user ID) instead of pinning `label='production'`, so each user stays on a consistent version during the test:

```python skip="true"
with prompt_var.get(targeting_key='tenant-123') as resolved:
    system_prompt = resolved.value
```

Watch the two versions in your traces and evaluations, and when `canary` proves reliable, move `production` to v2. See [Promote and roll out prompts](../reference/advanced/prompt-management/promotion-and-rollouts.md) for weights and targeting rules.

## The payoff

Your prompt is no longer a string frozen into a deploy. It's a versioned value you can:

- **change without shipping code**: save a version, move a label;
- **test before it's live**: in the editor or against a scored evaluation dataset;
- **promote and roll back in seconds**: a label move, not a redeploy;
- **audit**: every trace records which prompt version answered which request.

The prompt tweak that used to mean a code review and a full redeploy is now a label move you can undo instantly.

## Troubleshooting

- **The prompt always resolves to the default text?** Fetching prompts needs `LOGFIRE_API_KEY` (an API key with `project:read_variables` scope), not the write token. Without it, or if the label or slug doesn't exist yet, `logfire.var` silently falls back to `default`.
- **`ModuleNotFoundError` on `logfire.var`?** Install the variables extra: `pip install 'logfire[variables]'`.
- **Traces don't show a prompt label or version?** The model call has to run inside the `with prompt_var.get(...)` block so the span is tagged with what produced it.

## What's next

- [Prompt management concepts](../reference/advanced/prompt-management/concepts.md): the full model of prompts, versions, labels, and fragments.
- [Use prompts in your application](../reference/advanced/prompt-management/application.md): fetching and rendering prompts from your code, including runtime `{{...}}` inputs.
- [Promote and roll out prompts](../reference/advanced/prompt-management/promotion-and-rollouts.md): canary rollouts, targeting rules, and measuring the change.
- [Evaluate your AI](../evaluate/overview.md): score a prompt version before you promote it.
- [Prompt Playground](../guides/web-ui/prompt-playground.md): for one-off prompt experiments against a captured trace, as opposed to prompts your application depends on.
