# Logfire vs Datadog

Datadog is a comprehensive enterprise monitoring platform. Logfire is an AI-native observability platform built on OpenTelemetry. While both offer APM capabilities, their architectures and pricing models are fundamentally different.

## Quick Comparison

| Feature | Logfire | Datadog |
|---------|---------|---------|
| **Architecture** | OpenTelemetry-native | Proprietary agents |
| **Pricing Model** | Per-span ($2/million)* | Per-host + ingestion + custom metrics |
| **Host Fees** | None | $15-40/host/month |
| **AI/LLM Support** | First-class, one function call | Add-on, separate product |
| **Query Language** | SQL (Postgres-compatible) | Proprietary |
| **Setup Complexity** | 3 lines of code | Agent deployment per host |
| **Autoscaling Impact** | Linear cost increase | High-water-mark billing spikes |

*Logfire Cloud Pro pricing. Enterprise pricing available on request.

## Pricing Comparison

| Scenario | Datadog | Logfire Cloud* | Savings |
|----------|---------|----------------|---------|
| Hobby (2 hosts, 5M spans) | $101/mo | $0/mo (free tier) | 100% |
| Startup (10 hosts, 100M spans) | $560/mo | $180/mo | 68% |
| Scale-up (50-150 hosts, 500M spans) | $9,860/mo | $980/mo | 90% |
| High-volume (500 hosts, 2B spans) | $33,550/mo | $3,980/mo | 88% |

*Logfire Cloud Pro pricing ($2/million spans). Enterprise pricing (self-hosting, SSO, custom retention) available on request.

## When to Choose Logfire

- **AI-native applications:** You're building with LLMs and want first-class AI observability
- **Cost predictability:** You want simple per-span pricing without host fees or metric surcharges
- **OpenTelemetry investment:** You want portable instrumentation, not vendor lock-in
- **Autoscaling/serverless:** Your infrastructure scales dynamically and you don't want billing surprises
- **SQL querying:** You prefer familiar SQL over learning a proprietary query language

## When to Choose Datadog

- **Existing investment:** You're already deeply integrated with Datadog's ecosystem
- **Infrastructure monitoring:** You need comprehensive infrastructure metrics alongside APM
- **Enterprise requirements:** You need specific compliance certifications or integrations Datadog offers

## Key Differences Explained

### Pricing Model: Per-Span vs Per-Host

**Datadog** charges per host ($15-40/month) plus data ingestion plus custom metrics. This creates several pain points:

- **Autoscaling penalties:** High-water-mark billing means a traffic spike that adds 10 temporary hosts bills you for all 10 all month
- **Custom metrics explosion:** OpenTelemetry metrics are treated as expensive "custom metrics" with cardinality charges
- **Unpredictable costs:** Multiple billing dimensions make forecasting difficult

**Logfire** charges $2 per million spans after a free tier. That's it. No host fees, no custom metrics fees, no ingestion surprises.

### AI/LLM Support

**Datadog** added LLM observability as a separate product. It works, but AI isn't central to the platform's design.

**Logfire** was built for the AI era. One function call (`logfire.instrument_openai()`) gives you:

- Token tracking and cost monitoring
- LLM-specific panels for conversations
- Tool call inspection
- Streaming support

### OpenTelemetry

**Datadog** uses proprietary agents. While they support OTel export, it's not the native path.

**Logfire** is OpenTelemetry-native. Any OTel instrumentation works automatically. Your instrumentation is portable: if you ever want to switch, your code doesn't change.

### Query Language — Essential for Agentic Coding

**Datadog** uses a proprietary query language for dashboards and analysis. This creates limitations:

- Learning curve for humans and AI alike
- Coding agents are constrained to anticipated queries
- Vendor lock-in for your analysis workflows

**Logfire** uses SQL with PostgreSQL-compatible syntax. This is a significant advantage for AI-assisted development:

- **No artificial limitations** — Ask any question, get any answer
- **AI assistants excel at SQL** — GPT-5, Claude, and coding agents write excellent SQL
- **Agentic workflows** — When coding agents debug your AI application, they can write arbitrary queries
- **Familiar syntax** — No new query language to learn

When you're iterating on AI applications with coding agents, the agent needs to understand production behavior. With SQL, it can ask any question. With proprietary DSLs, it's constrained to what someone anticipated.

## Migration Path

If you're considering migrating from Datadog:

1. Logfire accepts standard OTel data. Start sending traces without changing your app.
2. Run both in parallel during transition
3. Gradually migrate instrumentation to Logfire SDKs for the best experience

## Summary

**Choose Logfire** for AI-native observability with predictable pricing and OpenTelemetry portability.

**Choose Datadog** if you're deeply invested in their ecosystem or need their specific infrastructure monitoring capabilities.
