---
title: "Connect an existing OpenTelemetry Collector to Fleet | Logfire"
description: "Add the Collector's own opamp extension to a Collector you already run, so Fleet shows its health, components and configuration. Your configuration stays where it is."
---
# Connect an existing Collector

!!! warning "Experimental"

    Fleet is experimental and can change between releases. Contact [Logfire support](mailto:support@pydantic.dev) for access.

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

Fleet shows **No remote config** as the **Policy status** of such a Collector, and lists it under **Needs attention** as taking no remote policy. That is expected: its configuration stays in your files. To let Fleet manage a Collector's configuration, [install it with Fleet](collectors.md) instead.

## Before you start

- A Collector Contrib build, or your own build that includes `opampextension`. These steps were checked with Collector Contrib v0.161.0.
- Outbound HTTPS from the Collector to Logfire.
- `curl` and `jq` on the machine where you get the connection key. It doesn't have to be the Collector's machine.

## 1. Get an enrollment key

1. In **Fleet management**, open **Collectors**, select **Add Collector**, then **Host**.
2. Under **What to collect**, pick any policy. Fleet needs one to create the key, but the extension never runs it.
3. Select **Get install command** and copy the **enrollment key**. Logfire shows it once. You don't need the install command.

This key connects one Collector installation. To connect separate installations with one key, open a published host policy under **Policies** and select **Enroll hosts**, which makes a key for as many as you choose.

## 2. Exchange it for a connection key

The extension can't use the enrollment key itself: a Collector that connects with it is disconnected with `enrollment needs an agent that accepts connection settings`. Exchange it once for a **connection key**. For a project in the US region:

```bash
read -rs ENROLLMENT_KEY  # paste the enrollment key, then press Enter
jq -n --arg key "$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)" --arg name "my-gateway" \
  '{registration_key: $key, name: $name}' |
  curl --fail --silent --show-error \
    --header @<(printf 'Authorization: Bearer %s\n' "$ENROLLMENT_KEY") \
    --header 'Content-Type: application/json' \
    --data-binary @- \
    https://logfire-us.pydantic.dev/v1/fleet/enroll/ |
  (umask 077 && cat > fleet-connection.json)  # readable only by you
unset ENROLLMENT_KEY
jq '{opamp_url, name: .installation.name, expires: .credential.expires_at}' fleet-connection.json
```

The key goes to `curl` through a file descriptor, not its command line, so other users on the machine can't see it in the process list. This needs bash or zsh. Use `https://logfire-eu.pydantic.dev` for the EU region. `name` names this installation and its connection key in Fleet: use the Collector's role, such as `my-gateway`. `registration_key` is a new random ID.

`fleet-connection.json` holds the connection key in `token`. It lasts 90 days. Move it to your secret store, note `opamp_url`, and delete the file. If the file also has a `telemetry_token`, that's a Logfire write token you can use to send this Collector's data. It expires with the connection key.

## 3. Add the extension

Add the extension to your Collector configuration, and add `opamp` to the extensions you already list under `service.extensions`. Keep the ones you have: this example already runs `health_check`.

```yaml
extensions:
  health_check: {}  # one you already have
  opamp:
    server:
      ws:
        endpoint: wss://logfire-us.pydantic.dev/v1/opamp  # opamp_url from step 2
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

- `reports_effective_config` sends the Collector's running configuration to Fleet, where members of your project can read it. The Collector replaces values it treats as secrets, such as this `Authorization` header and exporter API keys, with `[REDACTED]`. A secret written into an ordinary field, such as a password inside an endpoint URL, is sent as is: move it into a secret setting or an environment variable reference, or set `reports_effective_config: false`.
- `otel.collector.role` is optional. Fleet shows it on the Collector, which helps tell Collectors apart.
- Leave `instance_uid` unset. The extension picks a new ID each time the Collector starts.
- Leave `accepts_restart_command` and `reports_raw_config` off. Fleet doesn't use them for this kind of Collector.

Many Collectors can share one connection key, such as every pod of a Deployment or DaemonSet. Fleet lists them under one installation. Your plan's Collector allowance counts each connected Collector.

To also send the Collector's data to Logfire, add an exporter with a [write token](../../../how-to-guides/create-write-tokens.md). See the [Collector overview](../../../how-to-guides/otel-collector/otel-collector-overview.md).

## 4. Check it in Fleet

Open **Collectors**. You should see the Collector within a few seconds, named by its host or pod name, with **Connection** connected and **Policy status** **No remote config**. Select it to see its health per component, the configuration it runs and its components.

## Troubleshooting

If the Collector doesn't appear, look for `opamp` in the Collector's own logs:

| Log message | Check |
| --- | --- |
| `Failed to connect to the OpAMP server` with `websocket: bad handshake` | The endpoint is `opamp_url` from step 2, and the connection key is current. An expired or revoked key fails the same way. |
| `enrollment needs an agent that accepts connection settings` | The Collector is using the enrollment key. Use the connection key from step 2. |

## Replace the connection key

The extension can't take a new connection key from Fleet, so it stops connecting when its key expires. Before then:

1. In **Fleet management**, select **Settings** and open the connection key. It has the `name` you sent in step 2.
2. Select **Issue a replacement key**. It lasts 90 days.
3. Set `LOGFIRE_OPAMP_TOKEN` to the new key on your Collectors and restart them.
4. Once they all show as connected, revoke the old key.

## Next steps

- [Manage Collectors](collectors.md): let Fleet install and configure a Collector.
- [Hosts](../hosts.md) and [Kubernetes](../kubernetes.md): see the metrics your Collectors send.
