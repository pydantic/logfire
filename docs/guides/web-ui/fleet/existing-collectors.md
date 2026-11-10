---
title: "Connect an existing OpenTelemetry Collector to Fleet | Logfire"
description: "Add the Collector's own opamp extension to a Collector you already run, so Fleet shows its health, components and configuration. Your configuration stays where it is."
---
# Connect an existing Collector

!!! note "Beta"

    Fleet is in beta and can change between releases.

If you already run an OpenTelemetry Collector and manage its configuration yourself, with Helm, GitOps or a file on disk, you can still see it in Fleet. Add the [`opamp` extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/opampextension) that ships in the Collector Contrib distribution and give it a Fleet connection key. The extension connects to Fleet over the Open Agent Management Protocol (OpAMP), the OpenTelemetry standard for managing telemetry software remotely. You don't install anything else.

## What you get

The extension reports to Fleet, but Fleet can't change the Collector.

| | `opamp` extension (this page) | Fleet install ([Manage Collectors](collectors.md)) |
| --- | --- | --- |
| Listed under **Collectors**, connected or disconnected | Yes | Yes |
| Health of each component | Yes | Yes |
| The configuration it runs, and its components | Yes | Yes |
| Collector policies, rollouts and **Restart** | No | Yes |
| Connection key renewed automatically | No: replace it before it expires | Yes |
| Setup | Edit your Collector's configuration | One command, or the Kubernetes bridge |

Fleet shows such a Collector with the **Policy status** **Report only**, and doesn't list it under **Needs attention**: its configuration stays in your files. To let Fleet manage a Collector's configuration, [install it with Fleet](collectors.md) instead.

## Before you start

- A Collector Contrib build, or your own build that includes `opampextension`. These steps were checked with Collector Contrib v0.161.0.
- Outbound HTTPS from the Collector to Logfire.

## 1. Get a connection key

1. In **Fleet management**, open **Collectors**, select **Add Collector**, then **Existing Collector**.
2. Enter a **Name** for this installation, such as the Collector's role (`gateway`), and an **Environment** to filter by in Fleet.
3. Select **Get connection key**.

Logfire shows the **connection key** once, with the `opamp` extension block for the next step. Copy the key to your secret store. It lasts 90 days.

The connection key isn't a Logfire API key or write token. It only lets Collectors report to Fleet, as this one installation.

## 2. Add the extension

Add the block Logfire shows to your Collector configuration, and add `opamp` to the extensions you already list under `service.extensions`. Keep the ones you have: this example already runs `health_check`.

```yaml
extensions:
  health_check: {}  # one you already have
  opamp:
    server:
      ws:
        endpoint: wss://logfire-us.pydantic.dev/v1/opamp  # the URL Logfire shows
        headers:
          Authorization: Bearer ${env:LOGFIRE_OPAMP_TOKEN}
    capabilities:
      reports_effective_config: true
      reports_health: true
      reports_available_components: true
    agent_description:
      non_identifying_attributes:
        otel.collector.role: gateway

service:
  extensions: [health_check, opamp]  # your existing extensions, plus opamp
```

Start the Collector with the connection key in `LOGFIRE_OPAMP_TOKEN`.

- `reports_effective_config` sends the Collector's running configuration to Fleet, where members of your project can read it. The Collector replaces values it treats as secrets, such as this `Authorization` header and exporter API keys, with `[REDACTED]`. A secret in an ordinary field, such as a password inside an endpoint URL, is sent as is, even when it comes from an environment variable: move it into a setting the component treats as a secret, or set `reports_effective_config: false`.
- `agent_description` and its `otel.collector.role` are optional, and not in the block Logfire shows. Fleet shows the role on the Collector, which helps tell Collectors apart.
- Leave `instance_uid` unset. The extension picks a new ID each time the Collector starts.
- Leave `accepts_restart_command` and `reports_raw_config` off. Fleet doesn't use them for this kind of Collector.

Many Collectors can share one connection key, such as every pod of a Deployment or DaemonSet. Fleet lists them under one installation. Your plan's Collector allowance counts each connected Collector.

To also send the Collector's data to Logfire, add an exporter with a [write token](../../../how-to-guides/create-write-tokens.md). See the [Collector overview](../../../how-to-guides/otel-collector/otel-collector-overview.md).

## 3. Check it in Fleet

Open **Collectors**. You should see the Collector within a few seconds, named by its host or pod name, with **Connection** connected and **Policy status** **Report only**. Select it to see its health per component, the configuration it runs and its components.

## Troubleshooting

If the Collector doesn't appear, look for `opamp` in the Collector's own logs:

| Log message | Check |
| --- | --- |
| `Failed to connect to the OpAMP server` with `websocket: bad handshake` | The endpoint is the URL Logfire showed in step 1, and the connection key is current. An expired or revoked key fails the same way. |
| `enrollment needs an agent that accepts connection settings` | The Collector is using an enrollment key, such as one from the **Host** setup. Get a connection key from **Existing Collector** instead. |

## Replace the connection key

The extension can't take a new connection key from Fleet, so it stops connecting when its key expires. Before then:

1. In **Fleet management**, select **Settings** and open the connection key. It has the **Name** you entered in step 1.
2. Select **Issue a replacement key**. It lasts 90 days.
3. Set `LOGFIRE_OPAMP_TOKEN` to the new key on your Collectors and restart them.
4. Once they all show as connected, revoke the old key.

## Next steps

- [Manage Collectors](collectors.md): let Fleet install and configure a Collector.
- [Hosts](../hosts.md) and [Kubernetes](../kubernetes.md): see the metrics your Collectors send.
