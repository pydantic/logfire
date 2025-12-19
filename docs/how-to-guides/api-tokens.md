**Logfire** provides API tokens for programmatic access to your organization and projects.
API tokens allow you to manage Logfire resources such as projects, tokens, alerts, dashboards, and channels
through the Logfire API.

!!! note "API tokens vs Write tokens vs Read tokens"

    - **Write tokens** (`LOGFIRE_TOKEN`) are used to *send* observability data to Logfire.
    - **Read tokens** are used to *query* data from Logfire via the [Query API](query-api.md).
    - **API tokens** (`LOGFIRE_API_TOKEN`) are used to *manage* Logfire resources programmatically.

## How to Create an API Token

To create an API token using the web interface:

1. Open the **Logfire** web interface at [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Click on your organization name in the left sidebar.
3. Click on the ⚙️ **Settings** tab.
4. Select **API Keys** from the left-hand menu.
5. Click on the **Create API Key** button.
6. Fill in the form:
    - **Name**: A descriptive name to identify the API key.
    - **Description** (optional): Additional details about the API key.
    - **Scopes**: Select the permissions this API key should have.
    - **Project**: Optionally scope the API key to a specific project, or allow access to all projects.
7. Click **Create**.

After creating the API token, you'll see a dialog with the token value.
**Copy this value and store it securely, it will not be shown again.**

### Available Scopes

API tokens can be configured with different scopes to control access:

| Scope | Description |
|-------|-------------|
| `project:read` | Read access to projects |
| `project:write` | Create, update, and delete projects |
| `project:write_token` | Create and revoke write tokens |
| `project:read_token` | Create and revoke read tokens |
| `project:read_alert` | Read alerts |
| `project:write_alert` | Create, update, and delete alerts |
| `project:read_dashboard` | Read dashboards |
| `project:write_dashboard` | Create, update, and delete dashboards |
| `organization:read_channel` | Read notification channels |
| `organization:write_channel` | Create, update, and delete notification channels |

## Using the API Client

Logfire provides Python clients to simplify programmatic access to the API.
Both synchronous and asynchronous clients are available.

```python
from logfire import LogfireAPIClient, AsyncLogfireAPIClient
```

!!! note "Additional required dependencies"

    To use the API clients, you need to install `httpx`:

    ```bash
    pip install httpx
    ```

### Authentication

The API client can be authenticated in several ways:

=== "Environment Variable"

    Set the `LOGFIRE_API_TOKEN` environment variable:

    ```bash
    export LOGFIRE_API_TOKEN='your-api-token'
    ```

    Then create the client:

    ```python
    from logfire import LogfireAPIClient

    client = LogfireAPIClient.from_env()
    ```

=== "Explicit Token"

    Pass the token directly to the client:

    ```python
    from logfire import LogfireAPIClient

    client = LogfireAPIClient(api_token='your-api-token')
    ```

=== "Via logfire.api_client()"

    If you have `LOGFIRE_API_TOKEN` set, you can use the convenience method:

    ```python
    import logfire

    client = logfire.api_client()
    ```

### Client Usage Examples

Here are examples of common operations using the API client:

=== "Sync"

    ```python
    from logfire import LogfireAPIClient

    def main():
        with LogfireAPIClient(api_token='your-api-token') as client:
            # List all projects
            projects = client.list_projects()
            for project in projects:
                print(f"Project: {project['project_name']}")

            # Get a specific project by name
            project = client.get_project_by_name('my-project')
            project_id = project['id']

            # Create a write token for the project
            write_token = client.create_write_token(project_id)
            print(f"New write token: {write_token['token']}")

            # List write tokens
            tokens = client.list_write_tokens(project_id)
            for token in tokens:
                print(f"Token: {token['token_prefix']}... created at {token['created_at']}")

            # Create a read token
            read_token = client.create_read_token(project_id)
            print(f"New read token: {read_token['token']}")

            # List notification channels
            channels = client.list_channels()
            for channel in channels:
                print(f"Channel: {channel['label']} ({channel['config']['type']})")


    if __name__ == '__main__':
        main()
    ```

=== "Async"

    ```python
    import asyncio
    from logfire import AsyncLogfireAPIClient

    async def main():
        async with AsyncLogfireAPIClient(api_token='your-api-token') as client:
            # List all projects
            projects = await client.list_projects()
            for project in projects:
                print(f"Project: {project['project_name']}")

            # Get a specific project by name
            project = await client.get_project_by_name('my-project')
            project_id = project['id']

            # Create a write token for the project
            write_token = await client.create_write_token(project_id)
            print(f"New write token: {write_token['token']}")

            # List write tokens
            tokens = await client.list_write_tokens(project_id)
            for token in tokens:
                print(f"Token: {token['token_prefix']}... created at {token['created_at']}")

            # Create a read token
            read_token = await client.create_read_token(project_id)
            print(f"New read token: {read_token['token']}")

            # List notification channels
            channels = await client.list_channels()
            for channel in channels:
                print(f"Channel: {channel['label']} ({channel['config']['type']})")


    if __name__ == '__main__':
        asyncio.run(main())
    ```

### Managing Projects

```python
from logfire import LogfireAPIClient

with LogfireAPIClient(api_token='your-api-token') as client:
    # Create a new project
    new_project = client.create_project(
        project_name='my-new-project',
        description='A project for my application',
        visibility='private',
    )
    print(f"Created project: {new_project['id']}")

    # Update a project
    updated = client.update_project(
        new_project['id'],
        description='Updated description',
    )

    # Delete a project
    client.delete_project(new_project['id'])
```

### Managing Alerts

```python
from datetime import timedelta
from logfire import LogfireAPIClient

with LogfireAPIClient(api_token='your-api-token') as client:
    project = client.get_project_by_name('my-project')

    # Get notification channels to use with alerts
    channels = client.list_channels()
    channel_ids = [ch['id'] for ch in channels]

    # Create an alert
    alert = client.create_alert(
        project['id'],
        name='Error Alert',
        description='Alert when errors occur',
        query="SELECT * FROM records WHERE level = 'error'",
        time_window=timedelta(minutes=5),
        frequency=timedelta(minutes=1),
        watermark=timedelta(seconds=30),
        channel_ids=channel_ids,
        notify_when='has_matches',
    )
    print(f"Created alert: {alert['id']}")

    # List alerts
    alerts = client.list_alerts(project['id'])
    for a in alerts:
        print(f"Alert: {a['name']} (active: {a['active']})")

    # Update an alert
    client.update_alert(
        project['id'],
        alert['id'],
        active=False,  # Disable the alert
    )

    # Delete an alert
    client.delete_alert(project['id'], alert['id'])
```

### Managing Notification Channels

```python
from logfire import LogfireAPIClient

with LogfireAPIClient(api_token='your-api-token') as client:
    # Create a webhook channel
    channel = client.create_channel(
        label='My Slack Webhook',
        config={
            'type': 'webhook',
            'url': 'https://hooks.slack.com/services/...',
            'format': 'slack-blockkit',
        },
    )
    print(f"Created channel: {channel['id']}")

    # Update a channel
    client.update_channel(
        channel['id'],
        label='Updated Label',
        active=True,
    )

    # Delete a channel
    client.delete_channel(channel['id'])
```

### Managing Dashboards

```python
from logfire import LogfireAPIClient

with LogfireAPIClient(api_token='your-api-token') as client:
    project = client.get_project_by_name('my-project')

    # List dashboards
    dashboards = client.list_dashboards(project['id'])
    for dashboard in dashboards:
        print(f"Dashboard: {dashboard['dashboard_name']} (slug: {dashboard['dashboard_slug']})")

    # Get a specific dashboard
    if dashboards:
        dashboard = client.get_dashboard(project['id'], dashboards[0]['id'])
        print(f"Dashboard definition: {dashboard}")
```

## Error Handling

The API client raises specific exceptions for different error conditions:

```python
from logfire import (
    LogfireAPIClient,
    LogfireAPIError,
    LogfireAPINotFoundError,
    LogfireAPIForbiddenError,
    LogfireAPIValidationError,
    LogfireAPIRateLimitError,
)

with LogfireAPIClient(api_token='your-api-token') as client:
    try:
        project = client.get_project_by_name('nonexistent-project')
    except LogfireAPINotFoundError:
        print("Project not found")
    except LogfireAPIForbiddenError:
        print("Permission denied - check your API token scopes")
    except LogfireAPIValidationError as e:
        print(f"Validation error: {e.response_body}")
    except LogfireAPIRateLimitError:
        print("Rate limit exceeded - wait and retry")
    except LogfireAPIError as e:
        print(f"API error: {e} (status: {e.status_code})")
```

## API Reference

### LogfireAPIClient / AsyncLogfireAPIClient

Both clients provide the same methods, with the async client returning coroutines.

#### Projects

| Method | Description |
|--------|-------------|
| `list_projects()` | List all projects accessible to the API token |
| `create_project(project_name, description?, visibility?)` | Create a new project |
| `get_project(project_id)` | Get a project by ID |
| `get_project_by_name(project_name)` | Get a project by name |
| `update_project(project_id, ...)` | Update a project |
| `delete_project(project_id)` | Delete a project |

#### Write Tokens

| Method | Description |
|--------|-------------|
| `list_write_tokens(project_id)` | List write tokens for a project |
| `create_write_token(project_id)` | Create a write token |
| `delete_write_token(project_id, token_id)` | Revoke a write token |

#### Read Tokens

| Method | Description |
|--------|-------------|
| `list_read_tokens(project_id)` | List read tokens for a project |
| `create_read_token(project_id)` | Create a read token |
| `delete_read_token(project_id, token_id)` | Revoke a read token |

#### Alerts

| Method | Description |
|--------|-------------|
| `list_alerts(project_id)` | List alerts for a project |
| `create_alert(project_id, ...)` | Create an alert |
| `get_alert(project_id, alert_id)` | Get a specific alert |
| `update_alert(project_id, alert_id, ...)` | Update an alert |
| `delete_alert(project_id, alert_id)` | Delete an alert |

#### Channels

| Method | Description |
|--------|-------------|
| `list_channels()` | List notification channels |
| `create_channel(label, config)` | Create a channel |
| `get_channel(channel_id)` | Get a specific channel |
| `update_channel(channel_id, ...)` | Update a channel |
| `delete_channel(channel_id)` | Delete a channel |

#### Dashboards

| Method | Description |
|--------|-------------|
| `list_dashboards(project_id)` | List dashboards for a project |
| `create_dashboard(project_id, name, slug, definition)` | Create a dashboard |
| `get_dashboard(project_id, dashboard_id)` | Get a specific dashboard |
| `update_dashboard(project_id, dashboard_id, ...)` | Update a dashboard |
| `delete_dashboard(project_id, dashboard_id)` | Delete a dashboard |
