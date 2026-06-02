---
title: Self-Hosted Logfire Examples
description: "Provider-specific Dex connector examples for self-hosted Logfire."
---
# Examples

Use these snippets as starting points for `logfire-dex.config.connectors` in your production values file. Keep the base PostgreSQL, object storage, and sizing configuration in [production requirements](./installation.md), then add the connector for your identity provider.

When creating an OAuth or OIDC application in your provider, use this callback URL:

```text
https://logfire.example.com/auth-api/callback
```

Replace `https://logfire.example.com` with your self-hosted Logfire URL.

## GitHub

Use the [Dex GitHub connector](https://dexidp.io/docs/connectors/github/) with a GitHub OAuth app.

```yaml
logfire-dex:
  env:
    - name: GITHUB_CLIENT_ID
      valueFrom:
        secretKeyRef:
          name: logfire-github-oauth
          key: client-id
    - name: GITHUB_CLIENT_SECRET
      valueFrom:
        secretKeyRef:
          name: logfire-github-oauth
          key: client-secret
  config:
    connectors:
      - type: github
        id: github
        name: GitHub
        config:
          clientID: $GITHUB_CLIENT_ID
          clientSecret: $GITHUB_CLIENT_SECRET
          getUserInfo: true
```

## Azure AD

Use the [Dex OIDC connector](https://dexidp.io/docs/connectors/oidc/) with a Microsoft Entra ID app registration.

```yaml
logfire-dex:
  env:
    - name: AZURE_CLIENT_ID
      valueFrom:
        secretKeyRef:
          name: logfire-azure-oauth
          key: client-id
    - name: AZURE_CLIENT_SECRET
      valueFrom:
        secretKeyRef:
          name: logfire-azure-oauth
          key: client-secret
  config:
    connectors:
      - type: oidc
        id: azuread
        name: Microsoft
        config:
          issuer: https://login.microsoftonline.com/TENANT_ID/v2.0
          clientID: $AZURE_CLIENT_ID
          clientSecret: $AZURE_CLIENT_SECRET
          insecureSkipEmailVerified: true
```

## Okta

Use the [Dex OIDC connector](https://dexidp.io/docs/connectors/oidc/) with an Okta web application.

```yaml
logfire-dex:
  env:
    - name: OKTA_CLIENT_ID
      valueFrom:
        secretKeyRef:
          name: logfire-okta-oauth
          key: client-id
    - name: OKTA_CLIENT_SECRET
      valueFrom:
        secretKeyRef:
          name: logfire-okta-oauth
          key: client-secret
  config:
    connectors:
      - type: oidc
        id: okta
        name: Okta
        config:
          issuer: https://OKTA_DOMAIN
          clientID: $OKTA_CLIENT_ID
          clientSecret: $OKTA_CLIENT_SECRET
          insecureSkipEmailVerified: true
```
