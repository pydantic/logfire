---
title: Self-Hosted Logfire Examples
description: "Examples for self-hosted Logfire."
---
# Examples

This page collects examples for self-hosted Logfire.

## SSO Provider Examples

Use these snippets as starting points for `logfire-dex.config.connectors` in your production values file. For the full connector reference, see the [Dex connectors documentation](https://dexidp.io/docs/connectors/).

When creating an OAuth or OIDC application in your provider, use this callback URL:

```text
https://logfire.example.com/auth-api/callback
```

Replace `https://logfire.example.com` with your self-hosted Logfire URL.

### GitHub

Create a GitHub OAuth app using the [GitHub OAuth app setup docs](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app).

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

### Azure AD

Create a Microsoft Entra ID app registration using the [Microsoft app registration docs](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app), then [add the redirect URI](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri).

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

### Okta

Create an Okta web application using the [Okta OIDC web app setup docs](https://developer.okta.com/docs/guides/sign-into-web-app-redirect/main/).

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

## Instance Admin Automation

Use an API key from the self-hosted admin organization with the `instance:admin` scope when you need to automate work across multiple organizations. Exchange it through the OAuth token endpoint for a short-lived bearer token scoped to the target organization, then call the regular public APIs with that returned token.

The exchanged token is organization-scoped. Request only the scopes the automation needs.

You can inspect the public API schema for your self-hosted instance at `https://logfire.example.com/api/docs`. Replace `https://logfire.example.com` with your instance URL.

Install `requests` if it is not already available:

```bash
python -m pip install requests
```

This example exchanges the instance-admin API key, then uses the returned organization token to list projects in the target organization:

```python skip-run="true" skip-reason="external-connection"
import requests

BASE_URL = 'https://logfire.example.com'
INSTANCE_ADMIN_TOKEN = '<instance-admin-api-key>'
TARGET_ORG = 'acme'
SCOPES = ['project:read', 'organization:create_project']

exchange_response = requests.post(
    f'{BASE_URL}/api/oauth/token',
    data={
        'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
        'subject_token': INSTANCE_ADMIN_TOKEN,
        'subject_token_type': 'urn:ietf:params:oauth:token-type:access_token',
        'audience': f'{BASE_URL}/{TARGET_ORG}',
        'scope': ' '.join(SCOPES),
        'expires_in': '900',
    },
    timeout=30,
)
exchange_response.raise_for_status()
organization_token = exchange_response.json()['access_token']

projects_response = requests.get(
    f'{BASE_URL}/api/v1/projects/',
    headers={'Authorization': f'Bearer {organization_token}'},
    timeout=30,
)
projects_response.raise_for_status()

print(f'Projects in {TARGET_ORG}:')
for project in projects_response.json():
    print(f'- {project["project_name"]}')
```
