---
title: Troubleshooting Self-Hosted Logfire
description: "Troubleshooting guide for self-hosted Logfire deployments, including meta project access and image pull checks."
---
# Troubleshooting Self-Hosted Logfire

Self-hosted Logfire sends its own internal telemetry to the `logfire-meta` organization. Start there when the deployment is running but behavior is unclear.

## Access the Meta Organization

On first install, the chart creates a frontend token for the `logfire-meta` organization.

Read the token from the release namespace:

```bash
kubectl -n logfire get secret logfire-meta-frontend-token \
  -o "jsonpath={.data.logfire-meta-frontend-token}" | base64 -d
```

Open the meta project with your hostname and token:

```text
https://logfire.example.com/logfire-meta/logfire-meta#token=LOGFIRE_META_FRONTEND_TOKEN
```

After you get access, create an invite link for your own user from **Settings** > **Invite** and give it the **Admin** organization role.

To find errors in the meta project, use this query filter:

```text
level >= 'error'
```

## No Traces in the Meta Organization

If the meta project has no traces, check the services involved in ingestion and internal telemetry export:

```bash
kubectl -n logfire get pods
kubectl -n logfire logs statefulset/logfire-ff-ingest
kubectl -n logfire logs deployment/logfire-ff-ingest-processor
kubectl -n logfire logs deployment/logfire-otel-collector
kubectl -n logfire logs deployment/logfire-ff-query-api
```

Common causes are PostgreSQL connectivity, object storage connectivity, image pull failures, or incorrect public URL/TLS settings.

## ErrImagePull or ImagePullBackOff

If pods cannot pull images, check that:

* The image pull secret exists in the same namespace as the Helm release.
* `imagePullSecrets` in your values file references that secret name.
* The secret was created from the current image pull key provided by Pydantic.

The [production requirements](./installation.md#image-pull-secret) page shows the expected secret shape.

## PostgreSQL Migration Failures

Backend and FusionFire migrations run before the main workloads are ready. If Helm times out or reports a failed migration job, inspect the migration logs:

```bash
kubectl -n logfire logs job/logfire-backend-migrations
kubectl -n logfire logs job/logfire-ff-migrations
```

Check that:

* `postgresDsn` points at the `crud` database.
* `postgresFFDsn` points at the `ff` database.
* Dex storage points at the `dex` database.
* Database users have owner permissions for their databases.
* The Kubernetes cluster can connect to the PostgreSQL host and port.

## Support

When asking for support, include:

* Chart version.
* Kubernetes version.
* A sanitized copy of your values file.
* Relevant pod, job, or Helm error messages.
