---
title: "Send Claude Platform traces to Logfire"
description: "Add Logfire as an OpenTelemetry destination in the Claude Console to see Claude Managed Agents sessions and Messages API requests in Logfire, nested under your own application's traces."
integration: otel
---

# Send Claude Platform traces to Logfire

See what Claude did for each request your app sends: every Claude Managed Agents turn, each model request, each tool the agent ran, and the tokens it used. Logfire shows them as a trace (the full journey of one request, made of nested spans). A span is one unit of work: a single operation, with a name, a start, and a duration.

The Claude Platform runs the Messages API and Claude Managed Agents. Anthropic's servers send these spans directly to Logfire using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. You set this up once in the Claude Console. Add `logfire.configure()` to your app as well, and Claude's spans appear inside your own traces.

!!! note "Beta"
    OpenTelemetry export from the Claude Platform is in beta at Anthropic. Span and attribute names can change between versions of the Claude SDK.

## What you'll capture

- **Managed Agents sessions:** an `anthropic.session.turn` span for each agent turn, which holds the conversation, and a span for each tool the agent ran in its sandbox, such as `bash`, with its input and output.
- **Messages API requests:** an `anthropic.messages.create` span for each request, with the prompt and the response, and a span for each server tool the API ran, such as web search.
- **Model requests:** an `anthropic.model_request` span for each model call, with its token usage.
- **Your application's side:** a span for each call your code makes with the Claude SDK, and a span for each tool that the SDK's tool runner runs in your process.

!!! warning "Prompts and responses are sent to Logfire"
    With **Full content**, spans include prompts, responses, and tool inputs and results. Anthropic's servers send this data directly to Logfire, so Logfire's [scrubbing](../../how-to-guides/scrubbing.md) (which hides sensitive values before your app sends them) does not apply to it. Choose **Metadata only** to send only identifiers, timing, status, and token counts.

## Before you start

You need:

- A Logfire project and a [write token](../../how-to-guides/create-write-tokens.md) (the credential that lets a service send data to a Logfire project), from your project's **Settings → Write tokens**.
- The **admin** role in your Claude Console organization.
- An Anthropic API key from the [Claude Console](https://platform.claude.com/settings/keys), to run the examples below.

## Step 1: Add Logfire as a destination in the Claude Console

1. Open the Console's [OpenTelemetry settings](https://platform.claude.com/settings/telemetry-destinations) and click **Add destination**.
2. Leave **Provider** set to **Custom**, and set **Name** to `Logfire`.
3. For **OTLP endpoint URL**, enter the base URL of your Logfire [data region](../../reference/data-regions.md), without a path:

    === "US"

        ```text
        https://logfire-us.pydantic.dev
        ```

    === "EU"

        ```text
        https://logfire-eu.pydantic.dev
        ```

4. Under **Request headers**, add a header named `Authorization`, with your write token as the value. Use the token as it is, without a `Bearer` prefix.
5. For **Content mode**, choose **Full content** to read conversations in Logfire, or **Metadata only** to leave them out.
6. For **Workspaces**, choose the Claude workspaces whose spans go to Logfire: **All**, **Selected**, or **All except**.
7. Click **Add destination**.

<figure markdown="span">
  ![Add destination form in the Claude Console, filled in for Logfire](../../images/logfire-screenshot-claude-platform-console-add-destination.png){ width="600" }
  <figcaption>The destination form, filled in for a US Logfire project</figcaption>
</figure>

To check the connection, open the destination's **⋮** menu and click **Test**. An `anthropic.test` span appears in Logfire's [Live view](../../guides/web-ui/live.md) within about a minute.

From now on, Claude's spans for every request in those workspaces arrive in Logfire with the service name `claude-platform`. You don't need to change your code for this. Each request starts its own trace.

## Step 2: Put Claude's spans inside your app's traces

Without this step, you see what Claude did but not which part of your app asked for it. With it, one trace shows your code, each call it made, and what Claude did for that call.

Install `logfire` and the Claude SDK:

```bash
pip install logfire anthropic
```

Call `logfire.configure()` before you create the Claude client. You don't need any other tracing setup: the Claude SDK sends its spans through Logfire, and with each request it tells the API which of your spans made the call.

=== "Claude Managed Agents"

    ```python hl_lines="5 7" skip-run="true" skip-reason="external-connection"
    from anthropic import Anthropic

    import logfire

    logfire.configure()

    client = Anthropic(open_telemetry={'traces': {'content_mode': 'content'}})

    with logfire.span('fibonacci agent'):
        environment = client.beta.environments.create(
            name='fibonacci-env',
            config={'type': 'cloud', 'networking': {'type': 'limited', 'allow_package_managers': True}},
        )
        agent = client.beta.agents.create(
            name='Fibonacci agent',
            model='claude-sonnet-5-5',
            system='You are a helpful coding assistant. Keep replies short.',
            tools=[{'type': 'agent_toolset_20260401'}],
        )
        session = client.beta.sessions.create(agent=agent.id, environment_id=environment.id)

        with client.beta.sessions.events.stream(session.id) as stream:
            client.beta.sessions.events.send(
                session.id,
                events=[
                    {
                        'type': 'user.message',
                        'content': [
                            {'type': 'text', 'text': 'Print the first 10 Fibonacci numbers with a one-line Python command.'}
                        ],
                    }
                ],
            )
            for event in stream:
                if event.type == 'agent.message':
                    print(''.join(block.text for block in event.content if block.type == 'text'))
                elif event.type == 'session.status_idle':
                    break
    ```

=== "Messages API"

    ```python hl_lines="5 7" skip-run="true" skip-reason="external-connection"
    from anthropic import Anthropic, beta_tool

    import logfire

    logfire.configure()

    client = Anthropic(open_telemetry={'traces': {'content_mode': 'content'}})


    @beta_tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city.

        Args:
            city: The city name, for example Berlin.
        """
        return f'Cloudy, 15°C in {city}'


    with logfire.span('answer question'):
        runner = client.beta.messages.tool_runner(
            model='claude-haiku-5-5',
            max_tokens=1024,
            tools=[get_weather],
            messages=[{'role': 'user', 'content': 'What is the weather in Berlin?'}],
        )
        for message in runner:
            pass
        print(message.content[-1].text)
    ```

`open_telemetry={'traces': {'content_mode': 'content'}}` adds prompts and responses to the spans from your app. Leave it out to keep them to metadata only, or set the environment variable `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content` instead.

To group several calls into one conversation, pass a `conversation_id`. The SDK records it as `gen_ai.conversation.id` on the spans from your app. It is sent in both content modes, so don't put personal data in it:

```python hl_lines="8" skip-run="true" skip-reason="external-connection"
from anthropic import Anthropic

import logfire

logfire.configure()

client = Anthropic()
conversation = client.with_options(open_telemetry={**client.open_telemetry, 'conversation_id': 'conv_42'})

conversation.messages.create(
    model='claude-haiku-5-5',
    max_tokens=100,
    messages=[{'role': 'user', 'content': 'Hello, Claude'}],
)
```

!!! warning "Don't also call `logfire.instrument_anthropic()`"
    The Claude SDK records its own calls here. If you also call [`logfire.instrument_anthropic()`](anthropic.md), Claude's spans lose their link to your trace and show up without a parent. Use this page's setup when you send Claude Platform spans to Logfire, and `instrument_anthropic()` when you don't.

These examples were checked with `anthropic` 1.14.0.

## Verify

1. In the Console's [OpenTelemetry settings](https://platform.claude.com/settings/telemetry-destinations), check that the **Delivery** column shows **Healthy**. This can take about a minute after the first span.

    <figure markdown="span">
      ![Claude Console destination list showing the Logfire destination as Healthy](../../images/logfire-screenshot-claude-platform-console-delivery.png){ width="700" }
    </figure>

2. Run an example, then open the [Live view](../../guides/web-ui/live.md). Within about a minute you should see a `fibonacci agent` or `answer question` trace. Expand it: under each call from your app you should see Claude's spans from the `claude-platform` service. Click an `anthropic.session.turn` span to read the agent's conversation.

<figure markdown="span">
  ![Logfire Live view of a Managed Agents session trace with the turn span open](../../images/logfire-screenshot-claude-platform-logfire-trace.png){ width="800" }
  <figcaption>A Managed Agents session in Logfire: your app's spans, Claude's spans, and the turn's conversation</figcaption>
</figure>

## Read your traces

**Where the content is.** In a Managed Agents session, the conversation is on the `anthropic.session.turn` span, and each tool's input and output is on its tool span. In a Messages API request, the prompt and the response are on `anthropic.messages.create`. The `anthropic.model_request` spans have token usage but no prompt or response, so an empty preview there doesn't mean content is missing.

**Find all the spans of one session.** A session can span several traces, for example when you send a later message from a new request. Every Claude span of a session has the `anthropic.session.id` attribute, so a [SQL query](../../guides/web-ui/explore.md) finds them all:

```sql
SELECT start_timestamp, span_name, duration
FROM records
WHERE attributes->>'anthropic.session.id' = 'sesn_...'
ORDER BY start_timestamp
```

**Count tokens.** The same usage appears on more than one span: a Messages API request has it on the span from your app, on Claude's `anthropic.messages.create` span, and on its `anthropic.model_request` spans. Because of this, the token totals that Logfire shows on a Messages API trace count each token twice. To count each token once, add up only the model request spans (and, for Managed Agents, outcome evaluation spans):

```sql
SELECT
  trace_id,
  sum((attributes->>'gen_ai.usage.input_tokens')::int) AS input_tokens,
  sum((attributes->>'gen_ai.usage.output_tokens')::int) AS output_tokens
FROM records
WHERE span_name IN ('anthropic.model_request', 'anthropic.session.outcome_evaluation')
GROUP BY trace_id
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| **Delivery** shows **Failing** with status 401 or 403 | The `Authorization` header is wrong. Use a valid write token for this project, without a `Bearer` prefix. |
| **Delivery** shows **Failing** with status 404 | The **OTLP endpoint URL** has a path. Use only the base URL, such as `https://logfire-us.pydantic.dev`. |
| **Delivery** shows **Disabled** | Anthropic turns a destination off after 24 hours of failed deliveries. Fix the cause, then click **Enable** in the destination's **⋮** menu. Spans from while it was disabled are not sent later. |
| **Test** works but your requests don't appear | The destination doesn't cover the workspace of your API key. Check **Workspaces** on the destination. |
| Claude's spans are in their own traces | Call `logfire.configure()` before you create the client, make the calls inside one of your own spans, and don't call `logfire.instrument_anthropic()` in the same app. |
| Spans have no prompts or responses | The destination is set to **Metadata only**: edit it and choose **Full content**. If your organization has a HIPAA, FERPA, or K-12 data agreement with Anthropic, destinations send metadata only. |

## Learn more

- Anthropic's [OpenTelemetry guide](https://platform.claude.com/docs/en/manage-claude/opentelemetry) covers content size limits, delivery, and the Admin API for creating destinations in code.
- The [span reference](https://platform.claude.com/docs/en/api/opentelemetry/spans) lists every span and attribute Claude sends.
- To trace Claude calls without the Claude Platform's export, for example on Amazon Bedrock, see the [Anthropic integration](anthropic.md).
