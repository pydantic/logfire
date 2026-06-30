---
title: Self-Hosted Logfire Overview
description: "Overview of self-hosted Pydantic Logfire, including production requirements and operational procedures."
---
# Self-Hosted Logfire Overview

Self-hosted Logfire runs the same product as the public Logfire deployment in your own Kubernetes environment. It is delivered through the official [Logfire Helm chart](https://github.com/pydantic/logfire-helm-chart).

Self-hosted Logfire is included in the [Enterprise plan](../../enterprise.md). Contact [sales@pydantic.dev](mailto:sales@pydantic.dev) for access to the private container images and commercial terms.

Use the [Logfire Helm chart README](https://github.com/pydantic/logfire-helm-chart) for the current chart commands and chart-version-specific values. These website docs focus on planning, architecture, examples, and operational procedures.

## Website Docs

* [Local quickstart](./local-quickstart.md): run a first install with the chart's `values.dev.yaml` file.
* [Architecture](./architecture.md): understand the main services, dependencies, and data flow.
* [Production requirements](./installation.md): plan the production values you need before installing the chart.
* [Examples](./examples.md): configure SSO connectors and exchange instance-admin tokens.
* [Troubleshooting](./troubleshooting.md): debug image pull, database, and runtime issues.
* [Bucket migration](./bucket-migration.md): migrate telemetry object storage buckets.
* [Usage report](./usage-report.md): generate usage reports for self-hosted deployments.

## Production Prerequisites

A production deployment needs:

* A Kubernetes cluster with enough capacity for the selected sizing preset.
* Image pull credentials for Logfire's private images.
* PostgreSQL 16 or later.
* Three PostgreSQL databases: one for Logfire application data, one for FusionFire metadata, and one for Dex.
* Object storage using Amazon S3, Google Cloud Storage, Azure Storage, or an S3-compatible provider.
* An identity provider supported by [Dex](https://dexidp.io/docs/connectors/).
* Kubernetes storage for scratch and ingest volumes, either through a default `StorageClass` or explicit storage class settings in values.

## Client Configuration

After deploying self-hosted Logfire, point the SDK at your Logfire base URL:

```python
import logfire

logfire.configure(
    advanced=logfire.AdvancedOptions(base_url='https://logfire.example.com'),
)
```

You can also authenticate the CLI against your self-hosted instance:

```bash
logfire --base-url="https://logfire.example.com" auth
```
