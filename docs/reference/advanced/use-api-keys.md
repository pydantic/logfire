---
title: "Using API Keys to Access Public APIs"
description: "Guide on how to create API keys and use them to call Logfire public APIs for managing organizations, projects, and other resources."
---

**Logfire** provides public APIs that allow you to programmatically manage your organizations, projects, and other resources. To access these APIs, you'll need to create an **API key**.

!!! note
API keys are for accessing the Logfire platform APIs, _not_ for sending telemetry data (traces, logs, metrics).
To send data to Logfire, use [write tokens](./create-write-tokens.md).

Use the Logfire API to automate resource management and integrate Logfire into your existing workflows.

- Projects & tokens: Create projects and generate write/read tokens programmatically—useful for CI/CD pipelines or dynamic environments
- Alerts & dashboards: Set up monitoring infrastructure as code
- Channels: Configure notification destinations (Slack, webhooks, etc.)
- Audit logs: Track changes across your organization

## API Documentation

Complete API reference (Swagger docs):

- **US Region**: [https://api-us.pydantic.dev/api/docs](https://api-us.pydantic.dev/api/docs)
- **EU Region**: [https://api-eu.pydantic.dev/api/docs](https://api-eu.pydantic.dev/api/docs)

Choose the endpoint that matches your account's [data region](../data-regions.md).

## Creating API Keys

### Organization API Key

Navigate to your organization, then **Settings → API Keys → New API Key**.

Organization API keys can be scoped to all projects or a specific project. See [API Key Scopes](#api-key-scopes) for available permissions.

### Project API Key

Navigate to your project, then **Settings → API Keys → New API Key**.

Project API keys are limited to the project where they were created.

!!! warning
Copy your API key when it's displayed—it won't be shown again.

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

## API Key Scopes

When creating an API key, you can select specific scopes to limit what actions the key can perform.
Available scopes depend on whether you're creating an organization or project API key:

| Scope                                | Organization API Key | Project API Key |
| ------------------------------------ | -------------------- | --------------- |
| Organization management (read/write) | ✓                    | —               |
| Member management                    | ✓                    | —               |
| Billing access                       | ✓                    | —               |
| Project settings (read/write)        | ✓                    | ✓               |
| Write tokens management              | ✓                    | ✓               |
| Read tokens management               | ✓                    | ✓               |
| Alerts management                    | ✓                    | ✓               |

Select only the scopes your application needs to follow the principle of least privilege.
