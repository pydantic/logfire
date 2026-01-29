---
title: How to Migrate to a New Logfire Project
description: Send data to multiple Logfire projects simultaneously for seamless migration.
---

# Migrate to a New Logfire Project

When migrating between Logfire projects (e.g., moving to a new organization,
testing a new setup), you can double-write data to both projects during the
transition period.

## Configuration

### Using Python

```python
import logfire

logfire.configure(
    token=['pylf_v1_us_old_project_token', 'pylf_v1_us_new_project_token'],
)
```

### Using Environment Variables

```bash
export LOGFIRE_TOKEN=pylf_v1_us_old_project_token,pylf_v1_us_new_project_token
```

All traces, metrics, and logs will now be sent to both projects.

## How It Works

Each token creates its own independent export pipeline with:

- Separate HTTP session (independent retry queues)
- Separate span processor for traces
- Separate metric reader for metrics
- Separate log processor for logs

All telemetry data (spans, metrics, logs) is sent to all configured projects simultaneously.

!!! note
    Console output remains unified and is not duplicated per token. Scrubbing,
    sampling, and baggage processors are shared and applied once before data is
    sent to all configured projects.

## Completing the Migration

Once you've verified data is flowing correctly to the new project:

1. Remove the old token from the list
2. Update your environment variable to only include the new token

```python
import logfire

# After migration is complete
logfire.configure(
    token='pylf_v1_us_new_project_token',
)
```

Or:

```bash
export LOGFIRE_TOKEN=pylf_v1_us_new_project_token
```
