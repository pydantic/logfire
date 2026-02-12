---
title: Export Retry Mechanism
description: How Logfire handles failed exports with disk-based retry and exponential backoff.
---

# Export Retry Mechanism

The Logfire SDK includes a robust retry mechanism for handling failed telemetry exports. This page explains how it works and what the warning messages mean.

## Understanding the Warning Message

You may occasionally see a warning like this in your logs:

```
logfire - WARNING - Currently retrying 1 failed export(s) (7877 bytes)
```

This message indicates that the SDK failed to send telemetry data to the Logfire servers and has handed off the export to a background retry system. This is **normal behavior** when there are transient network issues, brief connectivity blips, or temporary server load.

## How the Retry Mechanism Works

When the SDK fails to send telemetry data, it follows this process:

1. **Immediate retry**: Waits 1 second and retries once
2. **Disk-based retry**: If the immediate retry also fails, the payload is saved to disk and retried in a background daemon thread using exponential backoff

The disk-based retry system:

- Saves failed exports to a temporary directory to conserve memory
- Uses exponential backoff starting at 1 second, doubling on each failure up to a maximum of 128 seconds
- Adds proportional jitter to spread out retry attempts
- Logs warnings at most once per minute to avoid flooding your logs
- Stores up to 512MB of failed exports before dropping new ones

## When Is This a Problem?

| Scenario | Interpretation |
|----------|----------------|
| Occasional warnings with `retrying 1 failed export(s)` | **Normal** - exports are failing occasionally but recovering |
| The retry count grows (2, 3, 5+) | **Investigate** - exports have been consistently failing for multiple minutes |
| `dropping an export` error message | **Action needed** - the 512MB disk buffer is full, data is being lost |

## Non-Blocking Design

The retry mechanism is designed to minimize impact on your application:

- **Background thread**: Retries run in a daemon thread, so they do not block your application's main thread or async event loop
- **Data persistence**: Failed exports are saved to disk, so data won't be lost even if retries take a while
- **Automatic recovery**: Once connectivity is restored, the backlog is sent automatically
- **Graceful shutdown**: The daemon thread won't prevent your application from exiting

## Troubleshooting

If you're seeing frequent retry warnings:

1. **Check network connectivity**: Verify that outbound HTTPS requests to Logfire servers are not being blocked by firewalls or network policies

2. **Check for DNS issues**: Ensure DNS resolution is working correctly for Logfire endpoints

3. **Review resource usage**: High CPU or memory usage can cause network timeouts

4. **Upgrade the SDK**: Newer SDK versions have improved retry logic that may reduce the frequency of these warnings:

    ```bash
    pip install --upgrade logfire
    ```

5. **Adjust timeout settings**: If you're calling [`force_flush()`][logfire.Logfire.force_flush] (common in serverless environments), you can reduce the worst-case blocking time by lowering the OTLP timeout:

    ```bash
    export OTEL_EXPORTER_OTLP_TIMEOUT=5000  # 5 seconds instead of default 10
    ```

!!! note "Serverless Environments"
    In serverless environments like AWS Lambda, the SDK typically calls `force_flush()` at the end of each invocation. This is a blocking call that waits for exports to complete. If exports are failing, it could cause delays up to the configured timeout value.

## Configuration

The retry mechanism uses these default values:

| Setting | Value | Description |
|---------|-------|-------------|
| Max retry delay | 128 seconds | Maximum time between retry attempts |
| Max disk buffer | 512 MB | Maximum bytes of failed exports to store |
| Log interval | 60 seconds | Minimum time between warning messages |

These values are not currently configurable but are designed to work well for most use cases.
