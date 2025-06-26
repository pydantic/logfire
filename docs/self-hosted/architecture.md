# Logfire Self-Hosted Service Architecture

The Self-hosted deployment has a number of interdependent services that work to run logfire.  Each component can be scaled independently of others depending on the utilisation of the system.

## Service Dependency Diagram

```mermaid
graph
    %% Entry point
    LS[logfire-service:8080]

    %% Core services
    LB[logfire-backend:8000]
    RD[logfire-redis:6379]
    FIA[logfire-ff-ingest-api:8012]
    FQA[logfire-ff-query-api:8011]
    FCC[logfire-ff-cache:9001]
    MW[logfire-maintenance-worker]

    OS[(Object Storage)]
    PG[(Postgres DB)]

    %% Connections from entry point
    LS --> LB
    LS --> FIA

    FQA --> FCC
    FQA --> PG
    FQA --> RD
    FQA --> OS

    LB --> FQA
    LB --> RD

    FIA --> PG
    FIA --> RD
    FIA --> OS

    FCC --> OS

    MW --> PG
    MW --> OS


```

## Service Descriptions

### Entry Point
- `logfire-service` (Port 8080): Main entry point for the system

### Core Services
- `logfire-backend` (Port 8000): Backend service handling business logic, frontend and authentication
- `logfire-ff-ingest-api` (Port 8012): API for data ingestion
- `logfire-ff-query-api` (Port 8011): API for querying data
- `logfire-ff-maintenance-worker`:  Compaction and Maintenance Jobs
- `logfire-redis`: Live query streaming and autocomplete cache
- `logfire-ff-cache` (Port 9001 via `logfire-ff-conhash-cache` consistent hashing): Cache service
