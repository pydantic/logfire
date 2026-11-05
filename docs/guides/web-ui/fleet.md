---
title: "Fleet: manage Collectors and SDKs from Logfire | Logfire"
description: "Install and manage OpenTelemetry Collectors on hosts and Kubernetes, and change what your applications send, from Logfire with Fleet."
---
# Fleet

Change what your OpenTelemetry Collectors and applications collect, and where they send it, from Logfire: no config files to edit on each machine and no redeploys. Fleet is in **Beta**.

Fleet manages three kinds of client:

| Client | What Fleet changes | How it connects |
| --- | --- | --- |
| **Hosts** | The Collector's whole pipeline: what it collects from the machine and its applications, how it processes it, and where it sends it | `logfire collector install` installs a managed Collector as a service |
| **Kubernetes** | The Collectors in a cluster, through the [OpenTelemetry Operator](https://github.com/open-telemetry/opentelemetry-operator) | An Operator bridge in the cluster applies the policy's Collector resources |
| **Applications** | SDK settings: sampling, minimum log level, redaction and scrubbing, which signals to export | The Fleet SDK for Python, Node.js, Java, .NET or Go |

Each client takes its settings from a **policy**: a versioned set of settings you edit and publish in Logfire. Clients connect over the Open Agent Management Protocol ([OpAMP](https://opentelemetry.io/docs/specs/opamp/)), the OpenTelemetry standard for managing telemetry agents remotely. Each one reports its health and the settings it is running, so Fleet also shows what runs where.

To turn Fleet on, enable **Fleet** under [**Settings → Early access**](https://logfire.pydantic.dev/settings/early-access). The choice applies to your account in this browser, not automatically to every member. Then open Fleet from **Fleet overview** in the sidebar, or from the **Fleet** button on the **Hosts**, **Kubernetes** and **Services** pages.

## Add a host

One command installs a Collector as a service and connects it to Fleet. It works on Linux, macOS and Windows.

1. Open **Hosts** in Fleet and select **Add host**.
2. Choose what to collect. A new host policy starts from a template, such as host monitoring and file logs.
3. Choose the host's operating system and copy the enrollment key. Logfire shows it once.
4. Run the command Logfire shows on the host, and paste the key when it asks. On Linux:

    ```bash
    uvx --from 'logfire-cli>=0.1.17' logfire-cli --beta --region us --org <your-org> collector install \
      --project <your-project> --token-stdin --yes
    ```

    `--token-stdin` makes the installer ask for the key without showing it as you type. Use `--region eu` for the EU region. The installer asks for administrator access. The command needs [uv](https://docs.astral.sh/uv/getting-started/installation/). The host does not need to sign in to Logfire: the enrollment key places it in your project.

5. Keep the setup open. It shows when the host's first data arrives.

To install on many hosts, pipe the key from your secret store into `--token-stdin`, or set `LOGFIRE_COLLECTOR_ENROLLMENT_TOKEN` and leave `--token-stdin` out.

## Connect a Kubernetes cluster

Fleet manages a cluster's Collectors through the OpenTelemetry Operator. Logfire gives you a manifest for an Operator bridge: one small deployment in its own namespace that connects to Fleet and applies the policy's Collector resources.

1. Open **Kubernetes** in Fleet and select **Add Kubernetes**.
2. Choose a Kubernetes policy template and the namespaces its Collectors may run in.
3. Follow the steps Logfire shows: install cert-manager and the Operator if the cluster has neither, apply the bridge manifest, then create the Secrets with your connection key and a Logfire write token.

The bridge can create, update and delete Collector resources in any namespace. Logfire states the exact permissions before you apply the manifest.

## Connect an application

Applications connect to Fleet directly, without a Collector.

1. Open **Applications** in Fleet and select **Add application**.
2. Choose what your application uses. Install the package and load it the way Logfire shows:

    | Application uses | Requires | Install | Load it |
    | --- | --- | --- | --- |
    | Python with the Logfire SDK | Python 3.11+, Logfire 5.1+ | `pip install 'pydantic-opamp-otel[logfire]'` | Replace `logfire.configure()` with `pydantic_opamp_otel.configure_logfire()` |
    | Python with OpenTelemetry | Python 3.11+ | `pip install pydantic-opamp-otel` | Set `OTEL_PYTHON_DISTRO=opamp` and `OTEL_PYTHON_CONFIGURATOR=opamp`, then run `opentelemetry-instrument python app.py` |
    | Node.js with OpenTelemetry | Node.js 22+ | `npm install @pydantic/opamp-otel` | `node --import @pydantic/opamp-otel/register app.js` |
    | Java with the OpenTelemetry Java agent | Java 17+ | Download [`opamp-javaagent-extension-0.1.1.jar`](https://repo1.maven.org/maven2/dev/pydantic/opamp-javaagent-extension/0.1.1/opamp-javaagent-extension-0.1.1.jar) and the [Java agent 2.31.1](https://repo1.maven.org/maven2/io/opentelemetry/javaagent/opentelemetry-javaagent/2.31.1/opentelemetry-javaagent-2.31.1.jar) | `java -javaagent:opentelemetry-javaagent-2.31.1.jar -Dotel.javaagent.extensions=opamp-javaagent-extension-0.1.1.jar -jar app.jar` |
    | .NET with OpenTelemetry automatic instrumentation | .NET 8+ | `dotnet add package OpenTelemetry.AutoInstrumentation --version 1.17.0` and `dotnet add package Pydantic.OpAmp.AutoInstrumentation` | Set `OTEL_DOTNET_AUTO_PLUGINS` as Logfire shows, publish, then start with `./instrument.sh dotnet App.dll` |
    | Go with OpenTelemetry | Go 1.25+ | `go get github.com/pydantic/opamp-clients/go/opampotel@v0.2.0` | One setup call in `main`, shown in the Go guide |

3. Set the variables Logfire shows (`OTEL_OPAMP_ENDPOINT`, `OTEL_OPAMP_HEADERS` with your connection key, and `OTEL_SERVICE_NAME`) and restart the application.
4. Logfire shows when the application connects and applies its policy.

The connection key only manages settings. Your application keeps sending telemetry with its existing Logfire write token. Each language's guide is in [pydantic/opamp-clients](https://github.com/pydantic/opamp-clients).

## Change a policy

Try one change once an application is connected:

1. Open the application's policy and set **Minimum log level** to **Warn**.
2. Review and publish it.

Within seconds the application stops sending info logs to the [Live view](live.md), with no restart or deploy. Set it back to **Application controlled** to undo.

Collector policies work the same way: edit the pipeline, then publish a new version. Every published version stays in the policy's history. To roll a version out to some clients first, turn on **Use rollouts** in your project's Fleet settings.

## Limits

Your plan sets how many applications and Collector policies your organization can manage. Fleet shows your usage and the limit when you reach it.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No **Fleet overview** in the sidebar | Turn on **Fleet** under **Settings → Early access**. If it is on, your role needs permission to read Fleet: ask an organization admin. |
| A host never appears | Run the install command again with `--dry-run` to see each step. The host needs outbound HTTPS to Logfire. |
| An application shows as disconnected | Check that the Fleet SDK loads before your application starts. Its logs name connection and authentication errors. |
| A policy shows as failed on a client | Open the client in Fleet. It reports which setting it could not apply and why. |
