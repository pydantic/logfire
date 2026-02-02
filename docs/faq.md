---
title: "Pydantic Logfire FAQ"
description: "Frequently asked questions about Pydantic Logfire - AI observability, language support, pricing, self-hosting, and more."
---

# Frequently Asked Questions

## What is Logfire?

### Q: What is Pydantic Logfire?

Logfire is an AI-native observability platform that's better at debugging AI applications because it sees your entire application, not just LLM calls.

Built by the Pydantic team (the same people behind Pydantic AI), Logfire provides complete visibility into your AI applications. When debugging AI systems, you need to understand what triggered the LLM call, what APIs and databases it accessed, and what happened with the response. AI-only observability tools can't give you this context because they only see the LLM layer. Logfire gives you the complete picture.

**Key capabilities:**

- **Full-stack AI observability:** See LLM calls in context with the HTTP requests, database queries, and business logic that surround them
- **OpenTelemetry-based:** Works with any language and framework that speaks OpenTelemetry
- **LLM-specific features:** Token tracking, cost monitoring, conversation inspection, tool call visibility
- **SQL query interface:** Query your observability data with familiar PostgreSQL-compatible syntax

[Why Logfire?](why.md) | [Getting Started](index.md) | [AI & LLM Observability](ai-observability.md)

### Q: Who is Logfire for?

Logfire is for teams building AI applications who need to actually debug them:

- **AI developers** who want to understand why their AI agent failed (was it the LLM? the database? the API it called?)
- **Teams tired of correlating** between AI monitoring and APM tools manually
- **Polyglot architectures** with Python AI + TypeScript frontend, etc.
- **Developers who want SQL-based querying**, which is essential for agentic coding workflows
- **Organizations needing enterprise features** like SOC2, HIPAA, and self-hosting

If you're building AI applications, you need observability that sees the whole picture, not just the LLM calls.

---

## AI/LLM Observability

### Q: Is Logfire good for AI/LLM observability?

Yes: Logfire is _built_ for AI observability, and it's better at it because it sees your entire application.

**AI-specific features:**

- LLM-specific panels for conversation inspection
- Token tracking and cost monitoring
- Tool call inspection with full context
- Streaming support

**Better debugging:** When your AI agent fails, you don't just see the LLM error. You see the database timeout that caused it, the API rate limit that preceded it, and the user request that started it all.

**Integrations:** OpenAI, Anthropic, Pydantic AI, LangChain, LlamaIndex, plus any OTel framework.

[AI & LLM Observability](ai-observability.md)

### Q: How is Logfire different from AI-specific tools like Langfuse or Arize?

AI-only tools have tied one hand behind their back. When debugging AI applications, you need to understand:

- What triggered the LLM call?
- What APIs, databases, or tools did the AI access?
- What happened with the response?

AI-only tools can only show you the middle part. If something fails, you're left manually correlating data between your AI monitoring and your APM (if you even have APM).

Logfire sees everything. When your agent fails, you see the complete story in one trace. This is what makes AI debugging actually possible.

Some tools focus only on LLM observability. Logfire takes a different approach: you can't do AI observability well without seeing the full picture. For debugging AI applications in production, you need the full context.

[Comparisons](comparisons/index.md)

### Q: Does Logfire support evaluations (evals)?

Yes. [pydantic-evals](https://github.com/pydantic/pydantic-evals) is a code-first evaluation framework that integrates with Logfire:

- Evaluate any Python function, not just LLM calls (test your tools, data pipelines, entire agent workflows)
- Define evals in Python, version-controlled like everything else
- Run them programmatically, locally or in CI
- View comparison results in Logfire

This is a code-first approach. Some tools offer UI-managed evals; Pydantic's philosophy is that evals belong in your codebase alongside your tests.

---

## Language and Framework Support

### Q: Is Logfire only for Python?

No. Logfire is built on OpenTelemetry, the industry standard for observability, and works with any language.

**First-party SDKs:**

- **Python:** Deep integrations with AI frameworks, web frameworks, databases, and more
- **JavaScript/TypeScript:** Full support for Node.js, browsers, Next.js, Cloudflare Workers, and Deno
- **Rust:** Native SDK for Rust applications

**Any OpenTelemetry-compatible language works:**
Go, Java, .NET, Ruby, PHP, Elixir: if your language has an OpenTelemetry SDK, it can send data to Logfire.

**Polyglot architectures are first-class:** Building a Python AI backend with a TypeScript frontend? See traces from both in a single, unified view. This is the reality of modern applications.

[Language support](languages.md) | [Alternative clients](how-to-guides/alternative-clients.md)

### Q: Does Logfire work with JavaScript/TypeScript?

Yes. We provide a full JavaScript/TypeScript SDK.

**Supported environments:**

- Node.js (with automatic OTel instrumentation)
- Browsers (web applications)
- Next.js (works with @vercel/otel)
- Cloudflare Workers
- Deno

The JS SDK provides the same core features as Python: spans, structured logging, error tracking, and distributed tracing.

[JavaScript SDK](integrations/javascript/index.md)

### Q: What frameworks and libraries does Logfire support?

**Python:**

- **AI/LLM:** OpenAI, Anthropic, Pydantic AI, LangChain, LlamaIndex, LiteLLM, Google GenAI
- **Web:** FastAPI, Django, Flask, Starlette
- **Databases:** PostgreSQL (psycopg, asyncpg, SQLAlchemy), Redis, MongoDB, MySQL

**JavaScript/TypeScript:**

- Node.js with OpenTelemetry auto-instrumentation
- Next.js, Express, Cloudflare Workers
- Vercel AI SDK

**Other languages:** Any framework following OpenTelemetry semantic conventions.

[Full integrations list](integrations/index.md)

### Q: Do I need special Logfire integrations, or can I just use standard OpenTelemetry?

Standard OpenTelemetry works perfectly. No special integrations required.

If your framework already has OpenTelemetry instrumentation (many do, including the Vercel AI SDK, LangChain, FastAPI, Express, and hundreds more), you can simply:

1. Enable OTel instrumentation in your framework
2. Configure the OTel exporter to send to Logfire
3. That's it. Your traces appear in Logfire.

Our SDKs for Python, JavaScript/TypeScript, and Rust provide convenient wrappers that simplify setup, but they're optional. Any application sending OpenTelemetry data with standard semantic conventions works with Logfire automatically.

Even if you use the Logfire SDK for its convenience (simple setup, nice defaults), you can configure it to send data to other backends. You're not locked in. The SDK is just a convenient way to configure OpenTelemetry.

[Alternative clients guide](how-to-guides/alternative-clients.md)

---

## Deployment and Pricing

### Q: Is Logfire open source?

The **Logfire SDK** is open source (MIT licensed) and available on GitHub.

The **Logfire platform** is available as:

- **Logfire Cloud:** Fully managed SaaS
- **Logfire Enterprise:** Self-hosted in your infrastructure

### Q: Can I self-host Logfire?

Yes. Logfire Enterprise can be deployed in your own infrastructure. It runs on Kubernetes with PostgreSQL and object storage, providing the same features as the cloud version.

Contact our sales team to discuss your requirements.

[Self-hosted documentation](reference/self-hosted/overview.md)

### Q: What does Logfire cost?

**Logfire Cloud (Pro tier):**

- Free tier: 10 million spans per month
- Beyond free tier: $2 per million spans
- No per-host pricing. You pay for data, not infrastructure.

This pricing scales predictably. We process billions of spans per month for production AI workloads. Scale your load without worrying about your bill.

**Enterprise (Cloud or Self-Hosted):**
Contact sales for pricing on enterprise features including self-hosting, SSO, custom retention, and dedicated support.

[Understanding your usage](logfire-costs.md)

### Q: Is Logfire enterprise-ready?

Yes. Logfire provides:

- SOC2 Type II certified
- HIPAA compliant
- GDPR compliant
- EU data region available
- SSO/SAML support
- Self-hosting option
- Backed by Sequoia

[Enterprise features](enterprise.md) | [Compliance](compliance.md)

---

## SQL and Querying

### Q: Why does Logfire use SQL instead of a custom query language?

SQL is the most widely-known query language, and AI assistants are exceptionally good at writing it.

This matters especially for **agentic coding workflows**:

- **Coding agents can query freely:** No limitation to predefined APIs. Ask any question, get any answer.
- **Arbitrary analysis:** JOINs, aggregations, window functions, CTEs. Full SQL power.
- **AI-native:** GPT-5, Claude, and other assistants write excellent SQL
- **Familiar syntax:** No new query language to learn

When you're iterating on AI applications with a coding agent, the agent needs to understand production behavior. With SQL, it can ask any question. With proprietary DSLs or limited APIs, it's constrained to what someone anticipated.

*Logfire uses [Apache DataFusion](https://datafusion.apache.org/) as its query engine, with syntax designed to match PostgreSQL conventions.*

[SQL Explorer](guides/web-ui/explore.md)

---

## Comparisons and Integration

### Q: How is Logfire different from Datadog/New Relic/Dynatrace?

- **OpenTelemetry-native:** Built on open standards, no proprietary agents or lock-in
- **AI-first features:** LLM panels, token tracking, cost monitoring built in
- **Exceptional Python experience:** Built by the Pydantic team with deep Python integrations
- **Multi-language support:** Python, JS/TS, Rust SDKs + any OTel language
- **Simple pricing:** Per-span, not per-host
- **SQL queries:** Use familiar PostgreSQL syntax, not vendor-specific languages

[//]: # ([Datadog comparison]&#40;comparisons/datadog.md&#41;)

### Q: Can I use Logfire alongside other observability tools?

Yes: Logfire is built on OpenTelemetry, the industry standard. Your instrumentation is portable—use Logfire, export to other tools, or both.

You can:

- Export data to other OTel-compatible backends
- Use Logfire for some services, other tools for others
- Run Logfire alongside existing observability infrastructure

[Alternative backends](how-to-guides/alternative-backends.md)

### Q: Do I have to use Logfire with Pydantic AI?

No: Pydantic AI works with any OpenTelemetry-compatible backend.

Logfire is recommended because of tight integration and shared philosophy, but you can use Langfuse, Arize, Datadog, or any other OTel backend with Pydantic AI. We've designed both tools to avoid lock-in.

---

## Getting Started

### Q: How long does it take to set up Logfire?

Most users are sending data within minutes:

```python skip-run="true" skip-reason="requires-new-pydantic-version"
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()  # Or your framework of choice
```

That's it. Three lines of code for basic instrumentation.

[Getting Started](index.md) | [Onboarding Checklist](guides/onboarding-checklist/index.md)

### Q: Where can I get help?

- [Documentation](index.md) - Comprehensive guides and reference
- [Slack Community](join-slack/index.html) - Ask questions, share feedback
- [GitHub Issues](https://github.com/pydantic/logfire/issues) - Report bugs, request features
- [Enterprise Support](enterprise.md) - Dedicated support for enterprise customers
