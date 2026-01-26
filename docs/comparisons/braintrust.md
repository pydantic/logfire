# Logfire vs Braintrust

Braintrust is an AI evaluation and observability platform focused on LLM testing and prompt iteration. Logfire is an AI-native observability platform built on OpenTelemetry. While both help you build better AI applications, they emphasize different parts of the workflow.

## Quick Comparison

| Feature | Logfire                                                        | Braintrust |
|---------|----------------------------------------------------------------|------------|
| **Primary Focus** | AI observability for agents and apps                           | AI evaluation and testing |
| **Strength** | Production monitoring, debugging                               | Eval workflows, prompt iteration |
| **Non-AI Tracing** | Full support                                                   | Limited (requires raw OTel) |
| **Evaluation** | Integrated web-UI - code-based via `pydantic-evals` | UI workflows |
| **SQL Queries** | Yes (Postgres-compatible)                                      | Limited |
| **Framework Support** | Any OTel-compatible                                            | AI frameworks only |

## When to Choose Logfire

- **Production observability:** You need a scalable solution to monitor AI applications in production
- **Full-stack visibility:** You want AI + application monitoring unified
- **Debugging focus:** You're troubleshooting production issues
- **Code-first evals:** You prefer evals as code, version-controlled
- **SQL analysis:** You want to query your data with familiar SQL

## When to Choose Braintrust

- **Evaluation focus:** Your only need is UI-based AI evaluation workflows 
- **Prompt iteration:** You're heavily iterating on prompts and need that workflow
- **UI-driven evals:** You prefer managing evaluations through a UI
- **AI-only scope:** You don't need full application observability

## Key Differences Explained

### Complete Observability vs LLM-Only

**Braintrust** focuses on the LLM layer. It shows you:

- LLM calls and responses
- Evaluation results
- Prompt performance

**Logfire** provides full-stack observability:

- Everything Braintrust shows, plus...
- Database queries, API calls, file operations
- Complete distributed traces
- Real-time debugging
- MCP server integration
- Production scalability
- Complex querying using SQL

When your AI agent misbehaves, was it the model's reasoning or the data it received? Only full-stack observability tells you.

### Evaluation Philosophy

**Braintrust** provides UI-driven evaluation workflows. Define evals in their interface, run them, see results.

**Logfire** shows a rich visualization of evals (built on code using [pydantic-evals](https://github.com/pydantic/pydantic-evals?utm_source=braintrust_compare_docs)) on the UI:

- Evaluate AI, LLM calls, and Python functions (test tools, data pipelines, entire workflows)
- Evals are code, version-controlled like everything else
- Run locally, in CI/CD, anywhere
- Visualise evals comparison on UI
- Integrate with `pytest` or any testing framework
- Full type safety with [Pydantic](https://pydantic.dev?utm_source=braintrust_compare_docs)

Different philosophies: Choose based on your team's workflow.

### Non-AI Instrumentation

**Braintrust** focuses purely on AI. To instrument non-LLM parts of your application, you need to set up raw OpenTelemetry and send to their OTLP endpoint.

**Logfire** makes all instrumentation easy with first-class [integrations](https://logfire.pydantic.dev/docs/integrations/?utm_source=braintrust_compare_docs):

```python skip="true" skip-reason="incomplete"
import logfire
logfire.configure()
logfire.instrument_openai()     # AI
logfire.instrument_fastapi(app) # API
logfire.instrument_asyncpg()    # Database
```

Same simple interface for everything.

### SQL-Based Analysis — Essential for Agentic Coding

**Logfire** exposes your data via SQL with PostgreSQL-compatible syntax. This is a significant advantage for AI-assisted development:

- **No artificial limitations** — Ask any question, get any answer
- **AI assistants excel at SQL** — GPT-5, Claude, and coding agents write excellent SQL
- **Joins and complex queries allowed** - write joins on your trace queries and create dashboards, all in SQL
- **Agentic workflows** — When coding agents debug your AI application, they can write arbitrary queries
- **Familiar syntax** — No new query language to learn

When you're iterating on AI applications with coding agents, the agent needs to understand production behavior. With SQL, it can ask any question. With custom APIs, it's constrained to anticipated queries.

**Braintrust** has its own query interface, optimized for evaluation workflows but less flexible for ad-hoc analysis. It accepts SQL, but only for simple queries. Joins should be done using BQL (Braintrust Query Language).

## Using Together

Some teams use both:

- **Braintrust** for structured evaluation during development
- **Logfire** for production observability and debugging

Both support OpenTelemetry, so you can send the same trace data to both if needed.

## Summary

**Choose Logfire** for production AI observability with support full-stack visibility and code-first evaluations and visualizations.

**Choose Braintrust** if structured evaluation workflows are your primary (or only) need, and you prefer UI-driven evals management.

**Consider both** if you want Braintrust's evals workflows alongside Logfire's production observability and scalable performance.
