---
title: Self-Hosted Logfire Production Requirements
description: "Plan the external services that a production install of self-hosted Pydantic Logfire needs before you install the Helm chart."
---
# Production Requirements

Plan the services that self-hosted Logfire depends on, so that your first production install works. The Helm chart runs Logfire in Kubernetes. It does not create your production databases, object storage, Redis, or identity provider, so you provision these before you install.

This page explains what each service is for and what you decide about it. The exact requirements, such as minimum versions, permissions, and value names, can change between chart versions. The [Logfire Helm chart README](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire) states them for each release. Read the README of the chart version that you install: open its `logfire-<version>` tag from the [list of chart tags](https://github.com/pydantic/logfire-helm-chart/tags). The chart links on this page open the `main` branch, which can describe a newer chart than the one you install.

<span id="production-values-checklist"></span>
<span id="starter-values-shape"></span>

Start your values file from the chart's [`values.prod.yaml`](https://github.com/pydantic/logfire-helm-chart/blob/main/charts/logfire/values.prod.yaml). It has a placeholder for each service on this page.

## Image pull secret

Logfire images are private. Contact [sales@pydantic.dev](mailto:sales@pydantic.dev) to get the `key.json` file for your image pull credentials. The chart README step [Create the image pull secret](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#2-create-the-image-pull-secret) shows how to make the Kubernetes Secret from it.

## PostgreSQL

Logfire keeps its metadata in three PostgreSQL databases:

* `crud`: Logfire application data, such as organizations, projects, dashboards, and users.
* `ff`: metadata for FusionFire, the Logfire engine that stores and queries telemetry. The metadata describes the telemetry files in object storage.
* `dex`: data for Dex, the service that signs users in.

Telemetry payloads go to object storage, not PostgreSQL, so PostgreSQL stays small.

Decide whether to use a managed PostgreSQL service, whether the three databases share one instance, and whether a connection pooler sits in front of it. A connection pooler, such as PgBouncer, shares a small number of database connections between many clients.

The chart README section [PostgreSQL](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#postgresql) states the supported versions, the required extensions, and the database owner requirement. [Connection poolers](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#connection-poolers) states what a pooler must support. To move the `ff` database to another instance later, see [FusionFire database migration](./ff-database-migration.md).

## Object storage

Logfire stores telemetry in a bucket on Amazon S3, Google Cloud Storage, Azure Storage, or an S3-compatible service.

Decide how Logfire gets access to the bucket. A cloud identity for the Kubernetes service account, such as IAM roles for service accounts on AWS, avoids long-lived keys. Static keys from a Kubernetes Secret also work.

The bucket settings affect cost and correctness. Logfire deletes the files that it no longer needs, so object versioning and soft delete keep deleted files that you pay for. A lifecycle rule that deletes files by age removes files that Logfire still reads.

The chart README sections [Object storage](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#object-storage) and [Bucket settings](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#bucket-settings) explain how to give Logfire access to the bucket, and which bucket settings to use. To move to another bucket later, see [Bucket migration](./bucket-migration.md).

## Redis

Logfire uses Redis for live query streaming and for caches. The chart can deploy a Redis for evaluation. For production, use a managed Redis.

The chart README section [Redis](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#redis) states the supported version and topologies, the DSN format, and the TLS settings.

## Hostnames and exposure

Logfire needs one stable public hostname, for example `logfire.example.com`. Logfire uses it to make links and to allow browser requests from that origin.

Decide how traffic reaches Logfire: a Kubernetes Ingress, Gateway API, or a routing layer that you manage outside the chart. Every proxy on the path must allow WebSocket connections.

The chart README section [Hostnames and exposure](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#hostnames-and-exposure) gives the values for each option.

## Identity provider

Users sign in through [Dex](https://dexidp.io/docs/connectors/), an identity service that the chart deploys. Dex connects to your identity provider, such as GitHub, Microsoft Entra ID (Azure AD), or Okta, through a connector. Users can also sign in with an email address and a password.

Decide how users sign in:

* For single sign-on through your identity provider, create an OAuth app in that provider before you install, and configure a Dex connector for it.
* For password sign-in, set `auth.passwordLogin: true`, because `values.prod.yaml` turns it off. Also configure an SMTP server in the `smtp.*` values, so that Logfire can send email.

The chart README section [Authentication](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#authentication) gives the redirect URI and the sign-in settings. [SSO provider examples](./examples.md#sso-provider-examples) show complete connectors.

## Sizing and storage

The chart has sizing presets that set the resources and the autoscaling of every workload. Pick a preset from your expected traffic.

The cluster needs two things for the presets:

* HorizontalPodAutoscaler metrics, usually from metrics-server, so that workloads can scale.
* A default StorageClass, or a StorageClass that you name in your values, for the volumes that the chart creates.

The chart README section [Sizing](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#sizing) lists the presets and the resources that each one sets.

## Next steps

* [Install the chart](https://github.com/pydantic/logfire-helm-chart/tree/main/charts/logfire#3b-production-starter) with your production values.
* If the install fails, see [Troubleshooting](./troubleshooting.md).
