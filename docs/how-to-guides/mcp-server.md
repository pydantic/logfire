# Logfire MCP Server

**Logfire** has its own [MCP server](https://modelcontextprotocol.io/introduction), which
you can use on [Claude Desktop](https://claude.ai/download),
[Cursor](https://www.cursor.com/), and any other software that supports MCP Servers.

## Connect to the MCP server

Here's how to connect different clients to the MCP server:

### Cursor

You can configure Cursor by creating a `.cursor/mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "logfire": {
      "command": "uvx",
      "args": ["logfire-mcp", "--logfire-read-token=YOUR-TOKEN"],
    }
  }
}
```

!!! note
    You need to pass the token via the `--logfire-read-token` flag, because Cursor doesn't
    support the `env` field in the MCP configuration.

For more detailed information, you can check the
[Cursor documentation](https://docs.cursor.com/context/model-context-protocol).

### Claude Desktop

In Claude Desktop, go to Settings → Advanced and add the following MCP configuration:
```json
{
  "command": ["logfire-mcp"],
  "type": "stdio",
  "env": {
    "LOGFIRE_READ_TOKEN": "your_token"
  }
}
```

Check out the [MCP quickstart](https://modelcontextprotocol.io/quickstart/user)
for more information.

### Cline

When using [Cline](https://docs.cline.bot/), you can configure the
`cline_mcp_settings.json` file to connect to the MCP server:

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
