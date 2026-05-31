---
title: Logfire MCP Server Setup Guide
description: Learn how to use an MCP to allow LLMs to access OpenTelemetry traces and metrics through Logfire. Detailed configuration guide for Cursor and Claude.
---
# Logfire MCP Server

An [MCP (Model Context Protocol) server](https://modelcontextprotocol.io/introduction) that provides
access to OpenTelemetry traces and metrics through Logfire. This server enables LLMs to query your
application's telemetry data, analyze distributed traces, and perform custom queries using
**Logfire**'s OpenTelemetry-native API.

You can check the [Logfire MCP server](https://github.com/pydantic/logfire-mcp) repository
for more information.

Once connected, you can query telemetry data and manage dashboards, alerts, issues, and more.
For a full list of available tools, see [Available MCP Tools](#available-mcp-tools) at the end of this guide.

## Remote MCP Server (Recommended)

Pydantic Logfire provides a hosted remote MCP server that you can use without installing anything locally.
This is the easiest way to get started with the Logfire MCP server.

To use the remote MCP server, add the following configuration to your MCP client.

**Choose the endpoint that matches your Logfire data region:**

- **US region** — `https://logfire-us.pydantic.dev/mcp`
- **EU region** — `https://logfire-eu.pydantic.dev/mcp`

!!! note
    The remote MCP server handles authentication automatically through your browser. When you first connect,
    you'll be prompted to authenticate with your Pydantic Logfire account.

!!! note
    If you are running a self-hosted Logfire instance, replace the URL above with your own Logfire instance URL
    (e.g., `https://logfire.my-company.com/mcp`), as the remote MCP server is hosted alongside your Logfire deployment.

---

## Configuration with well-known MCP clients

The examples below use the **US region** endpoint. Replace the URL with `https://logfire-eu.pydantic.dev/mcp` if you are using the EU region.

### Cursor

Create a `.cursor/mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp"
    }
  }
}
```

For more detailed information, you can check the
[Cursor documentation](https://docs.cursor.com/context/model-context-protocol).

### Claude Code

Run the following command to add the Logfire MCP server:

```bash
claude mcp add logfire --transport http https://logfire-us.pydantic.dev/mcp
```

Then use the `/mcp` slash command within Claude Code to authenticate with your Logfire account.
This will open a browser window where you can complete the login process.

For more information, see the [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp#authenticate-with-remote-mcp-servers).

### Claude Desktop

Add to your Claude settings:

```json
{
  "mcpServers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp"
    }
  }
}
```

Check out the [MCP quickstart](https://modelcontextprotocol.io/quickstart/user)
for more information.

### Codex

Install the [Logfire plugin](skills.md#codex) from the Pydantic marketplace. The plugin configures the hosted
Logfire MCP server automatically — no separate MCP JSON configuration is required.

The Codex plugin currently configures the US endpoint. For EU projects, replace the MCP entry and re-authenticate:

```bash
codex mcp remove logfire
codex mcp add logfire --url https://logfire-eu.pydantic.dev/mcp
codex mcp login logfire
```

Start a new Codex conversation after switching so the MCP tools reload.

### Cline

Add to your Cline settings in `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp"
    }
  }
}
```

### VS Code

Make sure you [enabled MCP support in VS Code](https://code.visualstudio.com/docs/copilot/chat/mcp-servers#_enable-mcp-support-in-vs-code).

Create a `.vscode/mcp.json` file in your project's root directory:

```json
{
  "servers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp"
    }
  }
}
```

### Zed

Create a `.zed/settings.json` file in your project's root directory:

```json
{
  "context_servers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp"
    }
  }
}
```

---

## Sandboxed Environments

If browser-based authentication is not available (e.g. in sandboxed environments), generate an API key with at least the `project:read` scope from your organization or project settings, then use it as a Bearer token:

```json
{
  "mcpServers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-us.pydantic.dev/mcp",
      "headers": {
        "Authorization": "Bearer <your-logfire-api-key>"
      }
    }
  }
}
```

---

## Running Locally (Deprecated)

!!! warning
    If you still want to run the MCP server locally, refer to the [local mcp server documentation](https://github.com/pydantic/logfire-mcp/blob/main/OLD_README.md) for setup and configuration instructions.

---

## Available MCP Tools

The Logfire MCP server exposes tools for querying telemetry data and managing observability resources.
The table below lists the full tool set for the `/mcp` endpoint.

!!! note
    The tools visible to a given client depend on the token scopes granted to that client.
    If `/mcp/codemod` is enabled, that endpoint also provides `exec` and `help` tools.

| Tool family | What it does | Common tool names |
| --- | --- | --- |
| Query execution | Run SQL against telemetry data, inspect schema, and retrieve recent exceptions for a file. | `query_run`, `query_schema_reference`, `query_find_exceptions_in_file` |
| Projects and auth context | Discover accessible projects, inspect token context, and create Logfire UI links. | `project_list`, `token_info`, `project_logfire_link`, `project_logfire_ui_link` |
| Dashboards | Create, list, fetch, update, and delete dashboards and panels, including dashboard settings. | `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_update`, `dashboard_delete`, `dashboard_update_settings`, `dashboard_add_panel`, `dashboard_update_panel`, `dashboard_remove_panel` |
| Dashboard variables | Add, update, replace, or remove dashboard variables. | `dashboard_add_variable`, `dashboard_update_variable`, `dashboard_update_variables`, `dashboard_remove_variable` |
| Dashboard layout groups | Organize dashboard panels into groups and control group layout/visibility. | `dashboard_create_group`, `dashboard_delete_group`, `dashboard_rename_group`, `dashboard_toggle_group_collapse`, `dashboard_reorder_groups` |
| Alerts | Create and manage SQL-based alerts and inspect alert status/history. | `alert_create`, `alert_list`, `alert_get`, `alert_update`, `alert_delete`, `alert_status`, `alert_history` |
| Notification channels | Create and manage organization-level destinations for alert notifications (for example webhooks/Opsgenie). | `channel_create_webhook`, `channel_create_opsgenie`, `channel_list`, `channel_get`, `channel_update_webhook`, `channel_update_opsgenie`, `channel_delete` |
| Notification schedules | Create and manage schedule windows that gate alert notification delivery. | `schedule_create`, `schedule_list`, `schedule_get`, `schedule_update`, `schedule_delete` |
| Issue tracking | List tracked exception issues and triage them by state. | `issue_list`, `issue_set_states` |
| Managed variables (feature flags) | Create and manage variables, versions, labels, and rollout behavior. | `variable_create`, `variable_list`, `variable_get`, `variable_list_versions`, `variable_update`, `variable_delete`, `variable_update_rollout`, `variable_create_version`, `variable_assign_label` |
| Local development bootstrap | Create a local dev session (including token/env setup) for sending telemetry. | `local_dev_session` |
