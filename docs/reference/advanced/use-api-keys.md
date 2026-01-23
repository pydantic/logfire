---
title: "Using API Keys to Access Public APIs"
description: "Guide on how to create API keys and use them to call Logfire public APIs for managing organizations, projects, and other resources."
---

**Logfire** provides public APIs that allow you to programmatically manage your organizations, projects, and other resources.
To authenticate with these APIs, you need to create an **API Key**.

!!! note
    API keys are for accessing the Logfire management APIs, not for sending telemetry data (traces, logs, metrics).
    To send data to Logfire, use [write tokens](../../how-to-guides/create-write-tokens.md) instead.

## API Documentation

The full API documentation is available via Swagger:

- **US Region**: [https://api-us.pydantic.dev/api/docs](https://api-us.pydantic.dev/api/docs)
- **EU Region**: [https://api-eu.pydantic.dev/api/docs](https://api-eu.pydantic.dev/api/docs)

Choose the endpoint that matches your account's [data region](../data-regions.md).

## Creating API Keys

API keys can be created in two places, depending on the scope of access you need:

### Organization Settings

To create an API key with organization-level access:

1. Open the **Logfire** web interface at [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Click on your organization name in the left sidebar.
3. Click on the ⚙️ **Settings** tab.
4. Select **API Keys** from the left-hand menu.
5. Click on the **New API Key** button.

Organization API keys can have both **organization scopes** and **project scopes**. You can configure the key to be valid for:

- **All Projects**: The key will have access to all projects within the organization.
- **A specific project**: The key will only have access to the selected project.

### Project Settings

To create an API key with project-level access only:

1. Open the **Logfire** web interface at [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Select your project from the **Projects** section on the left-hand side of the page.
3. Click on the ⚙️ **Settings** tab in the top right corner of the page.
4. Select **API Keys** from the left-hand menu.
5. Click on the **New API Key** button.

Project API keys can only have **project scopes** and are limited to the specific project where they were created.

!!! warning
    After creating an API key, you'll see a dialog with the key value.
    **Copy this value and store it securely, it will not be shown again.**

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

**Organization Scopes** (available only for organization API keys):

- Organization management (read/write)
- Member management
- Billing access

**Project Scopes** (available for both organization and project API keys):

- Project settings (read/write)
- Write tokens management
- Read tokens management
- Alerts management

Select only the scopes your application needs to follow the principle of least privilege.
