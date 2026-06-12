---
title: "Using API Keys to Access Public APIs"
description: "Guide on how to create API keys and use them to call Logfire public APIs for managing organizations, projects, and other resources."
---

**Logfire** provides public APIs that allow you to programmatically manage your organizations, projects, and other resources. To access these APIs, you'll need to create an **API key**.

!!! info "Public APIs"
    API keys are primarily for accessing the Logfire platform APIs. Project-scoped API keys can also be granted OTLP scopes for telemetry ingestion or Query API access. Existing [write tokens](../../how-to-guides/create-write-tokens.md) remain supported for sending telemetry.

!!! tip "What you can do"
    **Available to all plans:**

    - **Projects**: List, create, update, and delete projects
    - **Write tokens**: Create, list, rotate, expire, and revoke write tokens
    - **Read tokens**: Create, list, rotate, expire, and revoke read tokens
    - **Alerts**: Create, list, update, and delete alerts with SQL-based conditions and notification channels
    - **Dashboards**: Create, list, update, and delete dashboards
    - **Notification channels**: Create, list, update, and delete notification destinations (Slack, webhooks, etc.)
    - **Variables**: Create, read, and update project variables
    - **External variables**: Evaluate variables marked as external through OFREP
    - **OTLP**: Send telemetry data and query OTLP data with project-scoped keys
    - **Gateway proxy**: Proxy AI model requests through a specific project gateway

    **Enterprise / Self-hosted only:**{ .enterprise }

    - **Audit logs**: List and retrieve audit log entries for your organization
    - **Billing usage**: View billing usage data for current and previous periods
    - **SCIM provisioning**: Manage users and groups via the SCIM protocol for identity provider integration
    - **Organization management** _(self-hosted only)_: Create, list, update, and delete organizations

## API Documentation

Complete API reference (Swagger docs):

- **US Region**: [https://api-us.pydantic.dev/api/docs](https://api-us.pydantic.dev/api/docs)
- **EU Region**: [https://api-eu.pydantic.dev/api/docs](https://api-eu.pydantic.dev/api/docs)

Choose the endpoint that matches your account's [data region](../data-regions.md).

## Creating API Keys

### Organization API Key

Navigate to your organization, then **Settings → API Keys → New API Key**.

Organization API keys can be scoped to all projects or a specific project. See API Key Scopes for available permissions.

### Project API Key

Navigate to your project, then **Settings → API Keys → New API Key**.

Project API keys are limited to the project where they were created.

!!! warning
    Copy your API key when it's displayed—it won't be shown again.

### Personal API Keys

When creating an API key, it can be marked as **personal**. A personal API key is tied to your user account rather than being a shared project or organization key.

- **Automatically deleted** when your account is removed from the project or organization.
- **Only visible to you** — you can only view and delete your own personal API keys.
- **Scoped to your permissions** — the key can only be granted scopes that your role allows.

Organization and project admins can choose whether to create a personal or non-personal API key. Non-admin members always create personal API keys.

## API Key Scopes

When creating an API key, set the scope to define which actions the key can perform.
Available scopes depend on whether you're creating an organization or project API key. In the UI, organization keys can optionally apply to all projects or to one selected project. Project keys are always tied to the project where you create them. Some scopes, including OTLP and gateway proxy scopes, require a single project and cannot be granted to personal API keys:

| Scope prefix / scope                                | Organization API Key | Project API Key |
| ---------------------------------------------------- | -------------------- | --------------- |
| `organization:*` organization management scopes       | ✓                    | —               |
| `project:*` project settings and resource scopes      | ✓                    | ✓               |
| `project:read_variables` / `project:write_variables` | ✓                    | ✓               |
| `project:read_external_variables`                    | ✓                    | ✓               |
| `project:read_otlp` / `project:write_otlp`           | ✓                    | ✓               |
| `project:gateway_proxy`                              | ✓                    | ✓               |

!!! info
    Select only the scopes your application needs to follow the principle of least privilege.

## Using API Keys

Once you have an API key, you can use it to authenticate requests to the Logfire public APIs.
Include the API key in the `Authorization` header as a Bearer token.

### Example: List Projects

Here's an example using `curl` to list all projects in your organization:

=== "US Region"

    ```bash
    curl -X GET "https://api-us.pydantic.dev/api/v1/projects/" \
      -H "Authorization: Bearer YOUR_API_KEY"
    ```

=== "EU Region"

    ```bash
    curl -X GET "https://api-eu.pydantic.dev/api/v1/projects/" \
      -H "Authorization: Bearer YOUR_API_KEY"
    ```

Replace `YOUR_API_KEY` with your actual API key.

### Example Response

A successful request will return a JSON response with your projects:

```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "project_name": "my-project",
    "created_at": "2024-05-24T11:18:22.704455Z",
    "description": null,
    "organization_name": "my-organization",
    "visibility": "public"
  }
]
```
