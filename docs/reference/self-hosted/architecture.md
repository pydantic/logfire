---
title: Self-Hosted Logfire Architecture
description: "Architecture overview for self-hosted Pydantic Logfire, including the main runtime paths and external dependencies."
---
# Self-Hosted Logfire Architecture

Self-hosted Logfire is made up of independent Kubernetes workloads plus production infrastructure that you provide. The exact rendered workloads depend on the Helm chart version and feature flags, so use the [Logfire Helm chart README](https://github.com/pydantic/logfire-helm-chart) and values reference for chart-version-specific details.

## Runtime Flow

```mermaid
graph
    Client[SDKs, browsers, and API clients]
    Edge[logfire-service]
    Frontend[logfire-frontend-service]
    Backend[logfire-backend]
    Ingest[logfire-ff-ingest]
    Processor[logfire-ff-ingest-processor]
    Query[logfire-ff-query-api]
    Crud[logfire-ff-crud-api]
    Cache[logfire-ff-cache-byte]
    Workers[maintenance and compaction workers]
    Dex[logfire-dex]
    Redis[logfire-redis]
    Postgres[(PostgreSQL)]
    ObjectStore[(Object Storage)]
    IdP[Identity Provider]

    Client --> Edge
    Edge --> Frontend
    Edge --> Backend
    Edge --> Ingest
    Backend --> Dex
    Dex --> IdP
    Backend --> Crud
    Backend --> Redis
    Ingest --> Processor
    Processor --> ObjectStore
    Processor --> Postgres
    Query --> Cache
    Query --> Postgres
    Query --> ObjectStore
    Crud --> Postgres
    Workers --> Postgres
    Workers --> ObjectStore
    Cache --> ObjectStore
```

## Workload Groups

* Edge and frontend: `logfire-service` routes public traffic; `logfire-frontend-service` serves frontend assets.
* Application backend: `logfire-backend` handles application APIs, authentication integration, and UI backend behavior.
* Ingest path: `logfire-ff-ingest` receives telemetry; `logfire-ff-ingest-processor` processes and writes it.
* Query path: `logfire-ff-query-api` reads telemetry from object storage and metadata from PostgreSQL. Some deployments can also render `logfire-ff-query-worker`.
* Metadata APIs: `logfire-ff-crud-api` handles project, organization, dashboard, and related metadata operations.
* Cache and coordination: `logfire-ff-cache-byte` backs query caching; `logfire-redis` supports live query streaming and autocomplete cache.
* Background work: `logfire-ff-maintenance-worker` and `logfire-ff-compaction-worker` handle maintenance and compaction.
* Identity: `logfire-dex` integrates Logfire with your identity provider.
* Internal telemetry: `logfire-otel-collector` sends Logfire's own telemetry to the meta project.
* Optional features: the chart can render feature-specific workloads such as `logfire-remote-mcp` and `logfire-ai-gateway`.

## External Dependencies

Self-hosted Logfire depends on production-grade infrastructure outside the chart:

* PostgreSQL stores application metadata, identity data, and FusionFire metadata for files in object storage.
* Object storage stores telemetry data.
* An identity provider supplies user authentication through Dex.
* Ingress, Gateway API, or your routing layer exposes `logfire-service` on a stable hostname.

Telemetry payloads are stored in object storage, not PostgreSQL.
