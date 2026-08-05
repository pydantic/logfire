# Agent framework documentation

These guides must describe integrations that users can reproduce. Treat every code sample and support claim as
product behavior, not illustrative pseudocode.

## Required standard

- Use the framework's real agent abstraction and make it execute a real framework tool. A direct model call,
  prompt invocation, generation helper, chain, or query engine is not an agent example.
- Do not add manual wrapper spans, synthetic agent spans, fake tool spans, or other telemetry solely to make the
  trace look complete. Show telemetry emitted by the framework, an official adapter, or a documented third-party
  instrumentor.
- If no complete OpenTelemetry integration exists, say so plainly. Do not present a custom callback or hand-written
  span bridge as supported integration.
- Name the telemetry path accurately: framework-native OpenTelemetry, first-party adapter, third-party
  instrumentation, or direct OpenTelemetry Protocol (OTLP) export.
- Separate ingestion from product interpretation. Valid OTLP can appear in Live and Explore without satisfying the
  semantic conventions needed by the specialized LLMs, Agents, conversations, or optimizer views.
- State exactly which spans and attributes were observed. Do not promise agent, tool, model, token, prompt, or
  conversation data unless the example emitted it in a real run.

## Verification before publishing

- Test the sample against current package releases using the exact installation and run commands in the guide.
- Confirm the native agent completed its tool call; process exit success or a model response alone is insufficient.
- Confirm telemetry was exported and inspect the resulting span names, attributes, and parent-child relationships.
- When a guide promises prompts, responses, or tool content, use the framework's documented content-capture option
  and verify the emitted attributes. Do not copy application inputs or outputs onto a manual span to satisfy this
  check. Distinguish content recorded on spans from content emitted only as span events or log records.
- Check TypeScript module mode and types, Python imports, Go compilation, Rust compilation, and .NET compilation as
  applicable. Pin versions only when a current API genuinely requires it, and explain why.
- Keep secrets in environment variables. Never commit tokens, credentials, copied authorization headers, or real
  prompt data.

Small deterministic local tools are encouraged because they prove that the framework's native tool loop ran without
requiring another external service. The tool and agent must still be real framework objects; the telemetry must come
from the documented integration path.
