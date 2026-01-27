# Logfire vs Arize Phoenix

Arize Phoenix is an ML observability platform focused on model monitoring, drift detection, and LLM tracing. Logfire is an AI-native observability platform built on OpenTelemetry. While both help you observe AI applications, they come from different backgrounds and serve different needs.

## Quick Comparison

| Feature              | Pydantic Logfire                                               | Arize Phoenix                                                   |
|----------------------|----------------------------------------------------------------|-----------------------------------------------------------------|
| **Primary Focus**    | AI observability for agents and apps                           | ML model monitoring                                             |
| **Strength**         | AI + application tracing                                       | Drift detection, model performance                              |
| **Non-AI Tracing**   | Full support                                                   | Limited                                                         |
| **Language Support** | Python, JS/TS, Rust (SDKs) + any OTel                          | Python-focused                                                  |
| **Evals**            | Integrated web-UI - Code-based via `pydantic-evals` | Integrated web-UI - Code-based via external library |
| **Pricing**          | Per-span ($2/million)*                                         | Usage-based                                                     |
| **Setup**            | 3 lines of code                                                | OTel-based (several lines of code)                              |
| **SQL Queries**      | Yes (Postgres-compatible)                                      | No. Use `SpanQuery` DSL                                         |

*Logfire Cloud pricing (Team or Growth plans). Enterprise pricing available [on request](https://calendar.app.google/k9pkeuNMmzJAJ4Mx5).

## When to Choose Logfire

- **Application observability:** Scalable AI Observability for LLMs, agents, and apps
- **Polyglot architecture:** You have services in all OTel supported languages, with native SDKs for Python, TypeScript/JavaScript, and Rust
- **Developer experience:** You want the quickest possible setup
- **SQL analysis:** You prefer querying with SQL rather than learning a new querying language
- **Unified tooling:** You don't want separate tools for AI and application monitoring
- **MCP Integration:** Ask questions about your tracing data to your favourite coding assistant 

## When to Choose Arize Phoenix

- **ML model monitoring:** You need drift detection and model performance analytics
- **Data science workflows:** Your team thinks in ML metrics, not application traces
- **Existing Arize investment:** You're already using Arize's broader platform
- **Experimentation focus:** You're doing heavy ML experimentation and need those tools

## Key Differences Explained

### Application Observability vs ML Monitoring

**Arize Phoenix** comes from the ML monitoring world. It excels at:

- Model drift detection
- Feature importance analysis
- ML performance metrics
- Evaluation workflows

**Logfire** comes from the application observability world. It excels at:

- AI, LLMs, and agents tracing data
- Code-base evaluation workflows visualisation
- Database, API, and service monitoring
- Real-time debugging with Live View
- SQL-based analysis
- Native connection to MCP to debug your app

### Full-Stack Visibility

When your AI application fails, you need to know why. Was it the model? The data? The infrastructure?

**Arize Phoenix** shows you the AI layer but has limited visibility into your application infrastructure.

**Logfire** is your AI observability tool that can *also* show you everything: user request, database query, LLM call, and API response. One trace, complete context.

### Developer Experience

**Logfire** setup:

```python skip="true" skip-reason="incomplete"
import logfire
logfire.configure()
logfire.instrument_openai()
```

Three lines, and you're observing AI calls with full application context.

**Arize Phoenix** requires more configuration, especially for non-AI instrumentation.

### Query Interface — Essential for Agentic Coding

**Logfire** uses SQL with PostgreSQL-compatible syntax. This is a significant advantage for AI-assisted development:

- **AI assistants excel at SQL** — GPT-5, Claude, and [coding agents write excellent SQL](https://pydantic.dev/articles/logfire-mcp-is-awesome?utm_source=arize_comparison_docs)
- **Agentic workflows** — When coding agents debug your AI application, they can write arbitrary queries
- **Familiar syntax** — No new query language to learn
- **No artificial limitations** — Ask any question, get any answer

When you're iterating on AI applications with coding agents, the agent needs to understand production behavior. With SQL, it can ask any question. With proprietary interfaces, it's constrained to anticipated queries.

**Arize Phoenix** has its own query interface optimized for ML metrics but less flexible for ad-hoc analysis.

## Complementary Use

Logfire and Arize Phoenix can work together:

- Use Logfire for AI observability and real-time debugging for your app
- Use Arize for specialized ML model monitoring and drift detection

Both support OpenTelemetry, making integration possible.

## Summary

**Choose Logfire** for AI application observability with excellent full-stack tracing and support.

**Choose Arize Phoenix** for specialized ML model monitoring, drift detection, and data science workflows.

**Consider both** if you need deep ML experimentation alongside first-class AI observability and full-stack monitoring.
