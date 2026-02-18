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

## Running Locally (Deprecated)

!!! warning
    Running the MCP server locally is deprecated. Please use the [Remote MCP Server](#remote-mcp-server-recommended) instead.
    The local server will continue to work, but we recommend migrating to the remote server for a better experience.

If you prefer to run the MCP server locally, you can use the [`logfire-mcp`](https://pypi.org/project/logfire-mcp/) package instead.

<div class="video-wrapper">
  <iframe width="560" height="315" src="https://www.youtube.com/embed/z56NOvrtG74" frameborder="0" allowfullscreen></iframe>
</div>

### Installation

You'll need a read token to use the MCP server locally. See
[Create Read Token](./query-api.md#how-to-create-a-read-token) for more information.

You can then start the MCP server with the following command:

```bash
LOGFIRE_READ_TOKEN=<your-token> uvx logfire-mcp@latest
```

!!! note
    The `uvx` command will download the PyPI package [`logfire-mcp`](https://pypi.org/project/logfire-mcp/),
    and run the `logfire-mcp` command.

### Configuration

The way to configure the MCP server depends on the software you're using.

!!! note
    If you are in the EU region, you need to set the `LOGFIRE_BASE_URL` environment variable to `https://api-eu.pydantic.dev`. You can also use the `--base-url` flag to set the base URL.

#### Cursor

[Cursor](https://www.cursor.com/) is a popular IDE that supports MCP servers. You can configure
it by creating a `.cursor/mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "logfire": {
      "command": "uvx",
      "args": ["logfire-mcp", "--read-token=YOUR-TOKEN"],
    }
  }
}
```

!!! note
    You need to pass the token via the `--read-token` flag, because Cursor doesn't
    support the `env` field in the MCP configuration.

For more detailed information, you can check the
[Cursor documentation](https://docs.cursor.com/context/model-context-protocol).

#### Claude Desktop

[Claude Desktop](https://claude.ai/download) is a desktop application for the popular
LLM Claude.

You can configure it to use the MCP server by adding the following configuration to the
`~/claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "logfire": {
      "command": "uvx",
      "args": [
        "logfire-mcp",
      ],
      "env": {
        "LOGFIRE_READ_TOKEN": "your_token"
      }
    }
  }
}
```

Check out the [MCP quickstart](https://modelcontextprotocol.io/quickstart/user)
for more information.

#### Claude Code

[Claude Code](https://claude.ai/code) is a coding tool that is used via CLI.

You can run the following command to add the Logfire MCP server to your Claude Code:

```bash
claude mcp add logfire -e LOGFIRE_READ_TOKEN="your-token" -- uvx logfire-mcp@latest
```

#### Cline

[Cline](https://docs.cline.bot/) is a popular chatbot platform that supports MCP servers.

You can configure it to use the MCP server by adding the following configuration to the
`cline_mcp_settings.json` file:

```json
{
  "mcpServers": {
    "logfire": {
      "command": "uvx",
      "args": [
        "logfire-mcp",
      ],
      "env": {
        "LOGFIRE_READ_TOKEN": "your_token"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### Tools

There are four tools available in the MCP server:

#### `find_exceptions_in_file`

Get the details about the 10 most recent exceptions on the file.

Arguments:

- `filepath` (string) - The path to the file to find exceptions in.
- `age` (integer) - Number of minutes to look back, e.g. 30 for last 30 minutes. Maximum allowed value is 7 days.

#### `arbitrary_query`

Run an arbitrary query on the Pydantic Logfire database.

Arguments:

- `query` (string) - The query to run, as a SQL string.
- `age` (integer) - Number of minutes to look back, e.g. 30 for last 30 minutes. Maximum allowed value is 7 days.

#### `logfire_link`

Creates a link to help the user to view the trace in the Logfire UI.

Arguments:

- `trace_id` (string) - The trace ID to link to.

#### `schema_reference`

The database schema for the Logfire DataFusion database.
