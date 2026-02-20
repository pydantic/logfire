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

## Remote MCP Server (Recommended)

Pydantic Logfire provides a hosted remote MCP server that you can use without installing anything locally.
This is the easiest way to get started with the Logfire MCP server.

To use the remote MCP server, add the following configuration to your MCP client.

**Choose the endpoint that matches your Logfire data region:**

- **US region** — `logfire-us.pydantic.dev`
- **EU region** — `logfire-eu.pydantic.dev`

For **US region** (`logfire-us.pydantic.dev`):

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

For **EU region** (`logfire-eu.pydantic.dev`):

```json
{
  "mcpServers": {
    "logfire": {
      "type": "http",
      "url": "https://logfire-eu.pydantic.dev/mcp"
    }
  }
}
```

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

Run the following command:

```bash
claude mcp add logfire --type http --url https://logfire-us.pydantic.dev/mcp
```

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

## Running Locally (Deprecated)

!!! warning
    If you still want to run the MCP server locally, refer to the [local mcp server documentation](https://github.com/pydantic/logfire-mcp/blob/main/OLD_README.md) for setup and configuration instructions.
