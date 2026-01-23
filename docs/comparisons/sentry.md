# Logfire vs Sentry

Sentry is a mature error monitoring platform. Logfire is an AI-native observability platform built on OpenTelemetry. While Sentry excels at catching and tracking errors, Logfire provides complete visibility into your application's behavior.

## Quick Comparison

| Feature | Logfire | Sentry |
|---------|---------|--------|
| **Primary Focus** | Full observability (logs, traces, AI) | Error monitoring |
| **AI/LLM Support** | First-class, automatic instrumentation | Basic (treats AI calls like any function) |
| **Logging** | Structured logs with full context | Limited, error-focused |
| **Live View** | Real-time "pending spans" | No equivalent |
| **Query Interface** | SQL (Postgres-compatible) | Custom UI |
| **Pricing** | Per-span ($2/million)* | Per-event + quotas |

*Logfire Cloud Pro pricing. Enterprise pricing available on request.

## When to Choose Logfire

- **Full observability:** You want logs, traces, AND error tracking in one tool
- **AI/LLM applications:** You need to observe prompts, responses, token usage
- **Real-time debugging:** You want to see what's happening right now, not just errors
- **SQL analysis:** You want to query your data with familiar SQL
- **Unified tooling:** You don't want to juggle Sentry + logging service + APM tool

## When to Choose Sentry

- **Error-focused workflow:** Your primary need is catching and triaging errors
- **Frontend error tracking:** You need robust JavaScript error tracking with source maps
- **Issue tracker integration:** You rely on deep integrations with Jira, GitHub Issues, etc.
- **Mature ecosystem:** You want battle-tested error handling with extensive documentation

## Key Differences Explained

### Complete Observability vs Just Errors

**Sentry** captures exceptions and performance issues. It's excellent at what it does, but it only shows you when things go wrong.

**Logfire** provides full observability:

- **Structured logs:** Every log with full context, not just errors
- **Distributed traces:** See requests flow through your entire system
- **Real-time monitoring:** Watch your application in real-time with "pending spans"
- **AI visibility:** Automatic instrumentation for LLM calls, tool invocations, and more

### AI/LLM Support

**Sentry** treats AI calls like any other function. You'll see that an error occurred, but you won't see:

- What prompt was sent
- What the model responded
- Token usage and costs
- Tool calls and their results

**Logfire** was built for AI applications. One function call gives you complete LLM visibility:

```python
import logfire
logfire.configure()
logfire.instrument_openai()  # That's it
```

### Live Debugging

**Sentry** shows you errors after they happen.

**Logfire** has a unique "pending spans" feature that shows you what's happening right now. Watch requests in real-time, see where they're spending time, debug performance issues as they occur.

### SQL-Powered Analytics — Essential for Agentic Coding

**Sentry** uses a custom UI for querying and filtering.

**Logfire** uses SQL with PostgreSQL-compatible syntax. This is a significant advantage for AI-assisted development:

- "Show me all FastAPI requests that called our LLM more than 3 times"
- "What's the average token usage by endpoint?"
- "Which users are hitting rate limits most often?"

AI assistants and coding agents are excellent at writing these queries. When you're iterating on AI applications with coding agents, the agent needs to understand production behavior. With SQL, it can ask any question—no artificial limitations. With custom UIs or APIs, it's constrained to anticipated queries.

## Migration Path

If you're using Sentry and want to add Logfire:

1. **Complementary use:** Many teams run both. Sentry for error alerting, Logfire for observability.
2. **Gradual transition:** Start with Logfire for AI/LLM monitoring, expand from there
3. **Full migration:** Replace Sentry entirely if you want unified tooling

## Summary

**Choose Logfire** for full observability including AI/LLM support, real-time debugging, and SQL-based analysis.

**Choose Sentry** if your primary need is error monitoring with mature issue tracking integrations.

**Consider both** if you want Sentry's error alerting alongside Logfire's broader observability.
