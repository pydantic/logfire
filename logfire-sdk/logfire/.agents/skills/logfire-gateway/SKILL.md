---
name: logfire-gateway
description: Configure an application's model calls to use the Pydantic AI Gateway. Use when the user asks to route application inference through Gateway, connect a Gateway key, or add a Gateway provider snippet. This does not configure or instrument coding agents.
---

# Configure an Application with Pydantic AI Gateway

For observing or routing Claude Code/Codex itself, use
[coding-agent setup](https://pydantic.dev/.well-known/agent-skills/logfire-coding-agents/SKILL.md) instead. Keep this
application workflow separate from coding-session recording and provider setup.

Preserve the user's confirmed project, region, provider, and existing credential
mechanism. An existing application Gateway key needs no CLI login or SDK write
token. To create a key through the CLI, follow the
[CLI Gateway credential procedure](https://pydantic.dev/.well-known/agent-skills/logfire-coding-agents/references/application-gateway.md).
Use the UI's Gateway Connect flow when CLI access is unavailable.

Use this skill for model traffic, provider routing, and Gateway credentials. It
is separate from `logfire-instrumentation`: a Logfire write token sends
telemetry, while a Gateway key authorizes model requests. Do not substitute one
for the other. Do not configure coding-agent providers, telemetry, or MCP integrations.

A prepared setup handoff may already identify the exact project and credentials.
Reuse it rather than repeating authentication or selecting another project.

## 1. Identify the application

Before changing files, inspect the repository and identify the existing model
client, model, provider, environment loader, and runnable entrypoint. If the
request names an application or the repository contains a clear inference
client, wire that application through Gateway. Preserve its provider protocol
and model unless the user requests a change.

If there is no inference application or the target is ambiguous, ask which
application the user wants to connect. Confirm a new application's purpose
before scaffolding it.

A Gateway setup request authorizes routing the selected application's model
calls through Gateway. Ordinary Logfire instrumentation does not imply that choice.

Continue this setup in the current agent. A prepared wizard handoff already
finished account and project selection. Do not invoke the wizard again or
launch another setup agent. Preserve the existing model client, provider
abstraction, dependency versions, and environment conventions.

## 2. Handle credentials without exposing them

Reuse an existing Gateway credential provided through the repository's secret
mechanism. Otherwise obtain a project-scoped Gateway key using the UI's Connect
flow or the [CLI credential procedure](https://pydantic.dev/.well-known/agent-skills/logfire-coding-agents/references/application-gateway.md).
Do not create a telemetry write token merely to configure an existing Gateway key.
Never print the one-time secret in a recorded terminal or agent messages.
Store it using the environment variable read by the selected SDK or Connect
snippet: `PYDANTIC_AI_GATEWAY_API_KEY` for Pydantic AI. For other clients, keep
the application's existing variable, or use `LOGFIRE_GATEWAY_API_KEY` and
explicitly read it into the client's API-key option. Setting a variable alone
does not make an arbitrary client consume it.
Keep unrelated values intact. For a local environment file, require a gitignored
regular file with user-only permissions, replace exactly one existing assignment
or insert one, and write the file atomically. Never stage or commit the
secret-bearing file or key to source control. Do not append duplicate assignments. If the existing
secret mechanism cannot be updated safely, ask the user to install the key
through their normal secret manager.

A downloaded Connect credential can use the same secret mechanism without
printing or sourcing the downloaded file. Never put a key in agent messages,
source code, logs, tests, or snapshots.

Use the environment variable expected by the selected SDK. Keep the key out of
browser code and client-side bundles. Key creation does not activate Gateway,
configure provider billing, or select a routing endpoint. If the public API
rejects creation because Gateway is inactive or permission is missing, explain
that specific prerequisite. Missing OAuth scope requires renewed consent with
the needed permission; provider activation or billing requires Gateway settings.
Do not activate paid provider access without the user's agreement. Reuse a
successfully created key; do not mint another key during a configuration retry.

## 3. Configure the detected application

Prefer the existing client and dependency versions. Make the smallest change
that preserves the application's current provider abstraction.

### Pydantic AI

Use the Gateway model form when the selected provider and model are known:

```python
from pydantic_ai import Agent

# Set PYDANTIC_AI_GATEWAY_API_KEY and PYDANTIC_AI_GATEWAY_BASE_URL from Connect.
agent = Agent('gateway/openai:gpt-5.2')
```

Set `PYDANTIC_AI_GATEWAY_BASE_URL` to the Gateway root URL supplied by Connect
for the selected region or self-hosted deployment, alongside the API key.
Use the Pydantic AI snippet's root URL, not a provider-specific endpoint copied
from another client's snippet. Preserve an explicitly configured matching URL;
do not rely on SDK region inference or a default to select the user's destination.

The normal credential is `PYDANTIC_AI_GATEWAY_API_KEY`. When the application
needs an explicit key or custom route, use the installed Pydantic AI version's
`gateway_provider()` and preserve the provider type and route from the Connect
handoff. Do not guess a provider slug from a model name.

### OpenAI-compatible clients

Use the exact Gateway base URL and route supplied by Connect, or derive the
documented regional route from the handoff and existing provider protocol. Read
the provider-specific examples in the Gateway documentation when needed. Preserve the
client's existing API shape and load its API key from the application's selected
environment variable into the client's API-key option through its normal environment
loading mechanism. Do not hard-code a regional URL when the handoff already
provides one. A self-hosted origin is not a hosted region: use its confirmed
Gateway resource and configured route, or ask for them. A documented provider
path alone does not prove that this organization has that route enabled.

### Anthropic, Google, and other native clients

Use the provider-specific Gateway snippet from Connect or the linked public
Gateway documentation for the selected region. Native
provider paths are not interchangeable: Anthropic, OpenAI Responses, Google,
Bedrock, and chat-completions routes have different URLs and request shapes.
Do not translate a native request into another protocol merely to make the
example compile.

## 4. Verify one real request

Explain that a live request sends its prompt to the selected provider through
Gateway and may incur usage charges. Use one small synthetic payload with no
application, customer, or secret data. An explicit request to configure and test
the selected route authorizes this bounded check; otherwise ask for approval
before sending it. Do not activate paid access or run production workloads as a test.

Run that request through the selected route. Check the
response and the application's normal error handling. A successful import,
configuration parse, or process exit is not proof that the request used the
Gateway.

If the project has a read-capable Logfire login, query the exact project for a
fresh Gateway request or open its Gateway activity view. Do not use the
send-only SDK write token for reads. If read verification is unavailable,
report the request response as verified and mark Logfire-side arrival as
unverified.

Run the project's formatter, type checker, build, and focused tests. Report the
exact provider, route, model, endpoint class, credential variable, request
result, and any unverified Logfire-side check. Never claim that a Gateway
request was observed when this session did not check it.

After setup, return the relevant project or Gateway view link. If provider
activation or another prerequisite prevents the request, report that blocker
and mark application inference as unverified.

## References

- [Pydantic AI Gateway documentation](https://pydantic.dev/docs/ai/overview/gateway/)
