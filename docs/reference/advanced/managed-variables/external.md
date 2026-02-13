# External Variables and OFREP

When you need to access managed variables from less trusted environments — client-side web applications, mobile apps, edge services, or third-party integrations — Logfire provides **external variables** and **OFREP** (OpenFeature Remote Evaluation Protocol) endpoints.

## How Variable Access Works

There are two fundamentally different ways to read managed variables, and the choice between them has important security and performance implications:

### Pull-Based (Logfire SDK)

When you use `logfire.variable.get()` (or the `.get()` method on a variable created with `logfire.var()`), the SDK **pulls the full variable configuration** from the server and evaluates it locally:

1. The SDK fetches all variable definitions, versions, labels, and rollout rules in a single request
2. A background thread polls for updates (or listens via SSE)
3. Each `.get()` call resolves the value **locally in memory** — no network request per evaluation

This is efficient for backend services, but it means the client has access to the **complete configuration**, including all version values.

**Requires:** `project:read_variables` scope.

### Server-Side Evaluation (OFREP)

The OFREP endpoints take a different approach — every evaluation is a **server-side request**:

1. The client sends a request with the variable key and an evaluation context (targeting key, attributes)
2. The server evaluates the variable using the context and returns only the resolved value
3. The client never sees the full configuration, other versions, or rollout rules

This is less efficient (one network request per evaluation or batch), but the full configuration is **never exposed** to the client. A client would have to brute-force individual keys to discover what variables exist.

**Requires:** `project:read_variables` or `project:read_external_variables` scope.

## External and Internal Variables

By default, variables are **internal** — they are only accessible with an API key that has the full `project:read_variables` scope. You can mark a variable as **external** to make it accessible with the more restricted `project:read_external_variables` scope.

- **Internal variables** (default): Only accessible with `project:read_variables`. Use this for sensitive configuration like internal prompts, pricing parameters, or anything you don't want exposed to client-side code.
- **External variables**: Accessible with either `project:read_variables` or `project:read_external_variables`. Use this for configuration that is safe to expose, like feature flags, UI theme settings, or public-facing behavior toggles.

### API Key Scopes for Variables

| Scope | Description |
|-------|-------------|
| `project:read_variables` | Read all variables (both external and internal) via SDK or OFREP |
| `project:read_external_variables` | Read only variables marked as external, **via OFREP only** |
| `project:write_variables` | Create, update, and delete variables and variable types |

!!! warning "API key scope and SDK access"
    An API key with only the `project:read_external_variables` scope **cannot be used with `logfire.variable.get()`** or any of the pull-based SDK variable methods. The SDK's pull-based approach requires `project:read_variables` because it fetches the full configuration. The `project:read_external_variables` scope only grants access to the OFREP evaluation endpoints.

### Setting a Variable as External

You can set a variable as external in the Logfire UI when creating a variable (via the "External" toggle on the create form) or on the variable's **Settings** tab. You can also set the `external` field when creating or updating a variable via the API. Variables default to internal (`external: false`) when created.

```python skip="true"
# When pushing variables, the 'external' field can be set in the variable definition
# via the API. For example, using the bulk upsert endpoint:
import httpx

httpx.post(
    'https://logfire-api.pydantic.dev/v1/variables/bulk/',
    headers={'Authorization': 'Bearer YOUR_API_KEY'},
    json=[
        {
            'name': 'feature_flag',
            'json_schema': {'type': 'boolean'},
            'rollout': {'labels': {}},
            'overrides': [],
            'external': True,  # Makes this variable accessible with read_external_variables scope
        },
    ],
)
```

### Typical Setup

1. Create an API key with `project:read_variables` for your backend services (full access to all variables via SDK)
2. Create a separate API key with only `project:read_external_variables` for client-side or less trusted environments (OFREP access to external variables only)
3. Mark variables as external that are safe to expose to those environments

## OpenFeature (OFREP) Endpoints

Logfire exposes managed variables via the OpenFeature Remote Evaluation Protocol (OFREP). These endpoints evaluate variables as feature flags using a targeting context.

**Endpoints (API base URL + paths):**

```text
POST /v1/ofrep/v1/evaluate/flags/{key}
POST /v1/ofrep/v1/evaluate/flags
```

**Request body (single or bulk):**

```json
{
  "context": {
    "targetingKey": "user-123",
    "plan": "enterprise",
    "region": "us-east"
  }
}
```

- `targetingKey` is required and is used for deterministic rollout selection.
- Any additional fields in `context` become attributes for override rules.
- The OFREP response maps labels to the `variant` field for compatibility with OpenFeature clients.

**Caching (bulk endpoint):**

- The bulk endpoint returns an `ETag` header.
- If the client sends `If-None-Match` with the same value, the server returns `304 Not Modified`.

These endpoints require an API key with the `project:read_variables` or `project:read_external_variables` scope. When using `project:read_external_variables`, only variables marked as external are returned in evaluations.

For a step-by-step guide on using OFREP to evaluate feature flags in a web frontend or other client application, see [Client-Side Feature Flags with OFREP](../../../how-to-guides/client-side-feature-flags.md).
