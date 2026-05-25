---
title: Self-Hosted Logfire Production Requirements
description: "Plan the production values required for self-hosted Pydantic Logfire, including PostgreSQL, object storage, authentication, and sizing."
---
# Production Requirements

Use this page to plan the production values you need before installing self-hosted Logfire. Use the [Logfire Helm chart README](https://github.com/pydantic/logfire-helm-chart) for the exact install commands, local evaluation flow, and chart-version-specific sizing preset details.

## Production Values Checklist

Before installing the chart, decide how you will configure:

* Image pull credentials.
* PostgreSQL databases and credentials.
* Object storage bucket/container and credentials.
* Dex identity provider connector.
* Production sizing preset: `standard`, `small`, or `tiny`.
* Storage classes if your cluster does not have a default `StorageClass`.

## Starter Values Shape

Your production values file should have this shape. Replace the placeholders with your environment details and load sensitive values from Kubernetes Secrets, External Secrets, or your secret manager where possible.

```yaml
imagePullSecrets:
  - logfire-image-key

sizingPreset: standard
adminEmail: sre@example.com

ingress:
  enabled: true
  tls: true
  hostnames:
    - logfire.example.com
  ingressClassName: nginx

objectStore:
  uri: s3://logfire-prod
  env:
    AWS_DEFAULT_REGION: us-east-1

postgresDsn: postgresql://logfire_crud:PASSWORD@postgres.example.com:5432/crud
postgresFFDsn: postgresql://logfire_ff:PASSWORD@postgres.example.com:5432/ff

logfire-dex:
  config:
    storage:
      type: postgres
      config:
        host: postgres.example.com
        port: 5432
        user: logfire_dex
        database: dex
        password: PASSWORD
        ssl:
          mode: require
    connectors:
      - type: github
        id: github
        name: GitHub
        config:
          clientID: GITHUB_CLIENT_ID
          clientSecret: GITHUB_CLIENT_SECRET
          getUserInfo: true
```

## Image Pull Secret

Logfire images are private. Contact [sales@pydantic.dev](mailto:sales@pydantic.dev) to get the `key.json` file used to create an image pull secret.

Create the secret in the same namespace as the Helm release:

```bash
kubectl -n logfire create secret docker-registry logfire-image-key \
  --docker-server=us-docker.pkg.dev \
  --docker-username=_json_key \
  --docker-password="$(cat key.json)" \
  --docker-email=YOUR-EMAIL@example.com
```

Then reference it from your values file:

```yaml
imagePullSecrets:
  - logfire-image-key
```

If you mirror Logfire images into your own registry, keep the chart version and mirrored image tags aligned.

## PostgreSQL

The Helm chart does not deploy production PostgreSQL. Use PostgreSQL 16 or later and make sure the `intarray` and `btree_gist` extensions can be enabled.

Create three databases. They can live on the same PostgreSQL instance:

* `crud`: Logfire application data such as organizations, projects, dashboards, and users.
* `ff`: FusionFire metadata for files stored in object storage.
* `dex`: Dex identity service storage.

Telemetry payloads are stored in object storage, not PostgreSQL.
Each database user needs owner permissions so chart migrations can create and update schemas.

You can provide the two Logfire database DSNs directly:

```yaml
postgresDsn: postgresql://logfire_crud:PASSWORD@postgres.example.com:5432/crud
postgresFFDsn: postgresql://logfire_ff:PASSWORD@postgres.example.com:5432/ff
```

Or reference an existing Kubernetes Secret with `postgresDsn` and `postgresFFDsn` keys:

```yaml
postgresSecret:
  enabled: true
  name: my-postgres-secret
```

Dex uses its own PostgreSQL configuration:

```yaml
logfire-dex:
  config:
    storage:
      type: postgres
      config:
        host: postgres.example.com
        port: 5432
        user: logfire_dex
        database: dex
        password: PASSWORD
        ssl:
          mode: require
```

Dex configuration can reference environment variables. Use this pattern if the password is stored in a Secret:

```yaml
logfire-dex:
  env:
    - name: DEX_POSTGRES_PASSWORD
      valueFrom:
        secretKeyRef:
          name: my-postgres-secret
          key: dex-password
  config:
    storage:
      type: postgres
      config:
        host: postgres.example.com
        port: 5432
        user: logfire_dex
        database: dex
        password: $DEX_POSTGRES_PASSWORD
        ssl:
          mode: require
```

## Object Storage

Set `objectStore.uri` to your bucket or container:

```yaml
objectStore:
  uri: s3://logfire-prod
```

Do not enable bucket versioning. Logfire manages its own data lifecycle, and bucket versioning can increase cost and interfere with lifecycle behavior.

For Amazon S3, prefer workload identity such as IRSA, EKS Pod Identity, or your platform's equivalent. If you need static credentials, load them from a Secret:

```yaml
objectStore:
  uri: s3://logfire-prod
  env:
    AWS_DEFAULT_REGION: us-east-1
    AWS_ACCESS_KEY_ID:
      valueFrom:
        secretKeyRef:
          name: logfire-object-storage
          key: access-key-id
    AWS_SECRET_ACCESS_KEY:
      valueFrom:
        secretKeyRef:
          name: logfire-object-storage
          key: secret-access-key
```

For Google Cloud Storage:

```yaml
objectStore:
  uri: gs://logfire-prod
  env:
    GOOGLE_SERVICE_ACCOUNT_KEY:
      valueFrom:
        secretKeyRef:
          name: logfire-object-storage
          key: service-account-key
```

For Azure Storage:

```yaml
objectStore:
  uri: az://logfire-prod
  env:
    AZURE_STORAGE_ACCOUNT_NAME: logfireprod
    AZURE_STORAGE_ACCOUNT_KEY:
      valueFrom:
        secretKeyRef:
          name: logfire-object-storage
          key: account-key
```

## Hostnames and Exposure

Logfire needs a stable hostname so it can generate correct public URLs and CORS headers.

For a standard Ingress:

```yaml
ingress:
  enabled: true
  tls: true
  hostnames:
    - logfire.example.com
  ingressClassName: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
```

If you expose `logfire-service` directly instead of rendering an Ingress, keep `ingress.enabled: false` and still set the public hostname and TLS behavior:

```yaml
ingress:
  enabled: false
  tls: true
  hostnames:
    - logfire.example.com
```

Gateway API is also supported. To have the chart create a Gateway and HTTPRoute:

```yaml
ingress:
  enabled: false
  tls: true
  hostnames:
    - logfire.example.com
  secretName: logfire-tls-cert

gateway:
  enabled: true
  create: true
  gatewayClassName: istio
```

## Identity Provider

Logfire uses [Dex](https://dexidp.io/docs/connectors/) for user authentication. Dex connector examples belong in your values file under `logfire-dex.config.connectors`.

For GitHub:

```yaml
logfire-dex:
  config:
    connectors:
      - type: github
        id: github
        name: GitHub
        config:
          clientID: GITHUB_CLIENT_ID
          clientSecret: GITHUB_CLIENT_SECRET
          getUserInfo: true
```

For Azure AD, Okta, and more detailed GitHub steps, see [examples](./examples.md).

## Sizing and Storage

Start production deployments with one of the chart's production sizing presets:

```yaml
sizingPreset: standard
```

Use `standard` for the default production starting point, `small` for lower-traffic production deployments, or `tiny` for the smallest production footprint. The [Helm chart README](https://github.com/pydantic/logfire-helm-chart#sizing) is the source of truth for preset behavior and any per-workload overrides.

Production clusters should have working HorizontalPodAutoscaler metrics before relying on the built-in presets. If your cluster has no default `StorageClass`, set the required storage class values for scratch and ingest volumes.
