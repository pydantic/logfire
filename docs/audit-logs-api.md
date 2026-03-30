---
title: "Logfire Audit Logs API"
description: "Retrieve organization activity logs for security monitoring, compliance reporting, and usage auditing with the Logfire Audit Logs API."
---

# Logfire audit logs API

## Overview

The Audit Logs API lets you retrieve activity logs for your organization. Each log entry records user actions such as logins, project updates, token changes, and more.

Use it for security monitoring, compliance reporting, and usage auditing.


## Base URL

| Region | URL |
|--------|-----|
| US | `https://api-us.pydantic.dev/api` |
| EU | `https://api-eu.pydantic.dev/api` |


## Authentication

**Type:** Bearer token

**Header:**
```
Authorization: Bearer <your_api_token>
```

**Generating a token:** Go to your Logfire organization > Settings > API Keys and generate a token with the `organizations:auditlog` scope.


## Endpoints

### List audit logs

```
GET /v1/audit-logs/
```

Retrieve all audit log entries for a given organization within a time window.

#### Query parameters

| Name         | Required | Type | Format | Description |
|--------------|----------|------|--------|-------------|
| `start_time` | Yes | string | `YYYY-MM-DDTHH:MM:SSZ` | Start of the time range (inclusive). |
| `end_time`   | No | string | `YYYY-MM-DDTHH:MM:SSZ` | End of the time range (exclusive). |
| `action`     | No | string | Enum: `LOGIN`, `LOGOUT`, `INSERT`, `UPDATE`, `DELETE` | Filter logs by action type. |

> **Note:** The maximum query window is 90 days. Requests exceeding this will return a `400 Bad Request`. Make multiple requests to retrieve records over a longer period.

#### Example request

```bash
curl "https://api-us.pydantic.dev/api/v1/audit-logs/?start_time=2025-06-01T00:00:00Z&end_time=2025-07-01T00:00:00Z" \
  -H "Authorization: Bearer <your_api_token>"
```

#### Example response

```json
[
  {
    "id": "a85fe9a8-d9c1-4bb0-b68f-f73ce1a202ae",
    "created_at": "2025-09-17T15:38:55.901406Z",
    "organization_name": "christophergs",
    "project_name": "fastapi-example",
    "user_name": "ChristopherGS",
    "action": "INSERT",
    "resource_type": "read_tokens",
    "record_id": "835a8e09-417c-4688-9c5a-9f5dc40cf744",
    "ip_address": "123.123.123.123"
  },
  {
    "id": "5d961928-38f6-41d3-a29e-26ac6f5158e0",
    "created_at": "2025-09-17T10:24:39.740984Z",
    "organization_name": "christophergs",
    "project_name": null,
    "user_name": "ChristopherGS",
    "action": "DELETE",
    "resource_type": "projects",
    "record_id": "90873b49-177f-46b1-af9a-137a22db096b",
    "ip_address": "123.123.123.123"
  }
]
```

### Fetch a specific audit log record

```
GET /v1/audit-logs/{audit_log_id}/
```

> **Note:** The trailing slash is required.

Retrieve the details of a single audit log entry by its unique ID. This includes the diff — exactly what changed.

#### Example request

```bash
curl "https://api-us.pydantic.dev/api/v1/audit-logs/c1cc14dc-a124-405f-aab4-603dbde4b6af/" \
  -H "Authorization: Bearer <your_api_token>"
```

#### Example response

```json
{
  "id": "c1cc14dc-a124-405f-aab4-603dbde4b6af",
  "created_at": "2025-09-17T16:32:25.355252Z",
  "organization_name": "christophergs",
  "project_name": "pai-streaming-example-update",
  "user_name": "ChristopherGS",
  "action": "UPDATE",
  "resource_type": "projects",
  "record_id": "7b05bb15-b3ca-446b-94ea-e83396e0be15",
  "ip_address": "123.123.123.123",
  "downgrade_patches": [
    {
      "op": "replace",
      "path": "/project_name",
      "value": "pai-streaming-example"
    },
    {
      "op": "replace",
      "path": "/description",
      "value": null
    }
  ],
  "metadata": null
}
```

#### Error responses

| Code | Description |
|------|-------------|
| `403 Forbidden` | The token does not have access to this organization. |
| `404 Not Found` | The specified audit log record does not exist. |


## Response fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique identifier for the log entry. |
| `created_at` | string (UTC datetime) | Timestamp of when the action occurred. |
| `organization_name` | string | Name of the organization. |
| `project_name` | string \| null | Project name, if applicable. |
| `user_name` | string | Username of the actor. |
| `action` | string | Action type: `LOGIN`, `LOGOUT`, `INSERT`, `UPDATE`, `DELETE`. |
| `resource_type` | string \| null | Resource affected (e.g., `projects`, `read_tokens`, `write_tokens`). |
| `record_id` | string \| null | ID of the resource affected. |
| `ip_address` | string \| null | IP address of the actor, if recorded. |
| `downgrade_patches` | array \| null | Details of what changed, i.e. the diff. |

---

## Notes

- Querying more than 90 days of logs at once is not supported.
- Audit log entries are immutable and represent a reliable source of truth.
- Use the single-record endpoint for forensic or targeted investigations.
