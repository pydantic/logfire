# Logfire vs LangSmith

LangSmith is the observability and evaluation platform from the LangChain team. Logfire, combined with Pydantic AI, offers a production-grade alternative built on software engineering fundamentals.

## Quick Comparison

| Feature | Logfire + Pydantic AI | LangSmith + LangChain |
|---------|---------------------|----------------------|
| **Foundation** | Pydantic (500M+ downloads), type-safe | LangChain, flexible/dynamic |
| **Structured Outputs** | Schema-validated responses | String parsing, partial validation |
| **Observability Scope** | Full-stack (AI + systems) | LLM-focused |
| **Standards** | 100% OpenTelemetry GenAI | Proprietary format |
| **Data Retention** | Configurable | 14 days (standard), 400 days (extended) |
| **Query Interface** | SQL (Postgres-compatible) | Custom UI |
| **Framework Lock-in** | Works with any framework | Best with LangChain |

## Pricing Comparison

| Tier | LangSmith | Logfire Cloud* |
|------|-----------|----------------|
| Standard (14 days retention) | ~$500/1M traces | ~$6-10/1M traces |
| Extended (400 days retention) | ~$5,000/1M traces | ~$6-10/1M traces |

*Logfire Cloud Pro pricing. Enterprise pricing available on request.

At scale, Logfire can be 50-100X cheaper than LangSmith. This isn't about Logfire being a "budget option". It's about architectural efficiency. Logfire's OpenTelemetry-native design avoids the overhead of proprietary trace formats, and our query engine (DataFusion) retrieves traces significantly faster.

## When to Choose Logfire + Pydantic AI

- **Production-grade requirements:** You need type safety, validation, and real software engineering practices
- **Full-stack visibility:** You want AI observability AND system observability in one tool
- **Open standards:** You want OTel-compatible instrumentation that isn't locked to one vendor
- **Framework flexibility:** You use multiple AI frameworks or may switch in the future
- **Long-term cost efficiency:** You're scaling and costs matter

## When to Choose LangSmith + LangChain

- **LangChain investment:** You're heavily invested in the LangChain ecosystem
- **R&D workflow:** You prioritize prompt iteration and playground features
- **Quick prototyping:** You value LangChain's flexibility for rapid experimentation

## Key Differences Explained

### Production-Grade Foundation

The Pydantic stack brings real software engineering practices to AI development:

- **Type safety:** Catch errors at development time, not in production
- **Validated outputs:** Pydantic AI enforces schema-validated responses, not string parsing
- **Battle-tested:** Pydantic has 500M+ monthly downloads, used by OpenAI, Anthropic, and most AI frameworks

### Full-Stack Observability

LangSmith shows you what your LLM did. Logfire shows you what your LLM did AND what happened in your databases, APIs, and services.

When your AI agent fails, you need to know: Was it the LLM reasoning? The tool that returned bad data? The database query that timed out? Only full-stack observability answers these questions.

### Open Standards

Logfire is built on OpenTelemetry with 100% GenAI semantic convention alignment. This means:

- Your instrumentation is portable
- You can use familiar OTel tooling
- You're not locked into any single vendor

Pydantic AI itself works with ANY observability backend that supports OTel. You're not locked into Logfire.

### SQL for Agentic Coding

Logfire uses SQL with PostgreSQL-compatible syntax for querying, not a proprietary UI or API. This is critical for AI-assisted development:

- **Coding agents can query freely** — No limitation to predefined queries
- **AI assistants excel at SQL** — GPT-5, Claude, and coding agents write excellent SQL
- **Arbitrary analysis** — JOINs, aggregations, window functions, CTEs—full analytical power
- **Familiar syntax** — No new query language to learn

When your coding agent needs to debug production issues, it can write whatever query answers the question. With custom UIs or APIs, it's limited to what someone anticipated.

### Evaluations

LangSmith includes built-in evaluation workflows. For Logfire users, [pydantic-evals](https://github.com/pydantic/pydantic-evals) provides a code-first approach to evaluations:

- Evaluate any Python function, not just LLM calls (test tools, data pipelines, entire workflows)
- Define evals as code, version control them
- Run locally or in CI/CD
- Integrate with any testing framework

Different philosophy: UI-managed vs code-first. Choose what fits your workflow.

## Summary

**Choose Logfire + Pydantic AI** for production-grade AI development with type safety, full-stack observability, and open standards.

**Choose LangSmith + LangChain** if you're invested in the LangChain ecosystem and prioritize R&D workflow features.
