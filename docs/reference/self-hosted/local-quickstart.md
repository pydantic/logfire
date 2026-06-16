---
title: Self-Hosted Logfire Local Quickstart
description: "Run self-hosted Pydantic Logfire locally with the Helm chart's development values."
---
# Local Quickstart

Use this path to evaluate a first self-hosted install on a local or test Kubernetes cluster. It uses the Helm chart's `values.dev.yaml` file, which deploys development-grade PostgreSQL, MinIO, and MailDev in the cluster.

!!! warning
    `values.dev.yaml` is only for local evaluation and testing. Do not use it for production deployments.

## Prerequisites

* A Kubernetes cluster, such as Kind, Minikube, or Docker Desktop.
* Helm.
* The Logfire image pull key from Pydantic.

## Install

Create the namespace and image pull secret:

```bash
kubectl create namespace logfire
kubectl -n logfire create secret docker-registry logfire-image-key \
  --docker-server=us-docker.pkg.dev \
  --docker-username=_json_key \
  --docker-password="$(cat key.json)" \
  --docker-email=YOUR-EMAIL@example.com
```

Install the chart with the development values file:

```bash
helm repo add pydantic https://charts.pydantic.dev/
helm repo update
helm pull pydantic/logfire --untar
helm upgrade --install logfire ./logfire \
  -f ./logfire/values.dev.yaml \
  --namespace logfire
```

Port-forward Logfire:

```bash
kubectl -n logfire port-forward svc/logfire-service 8080:8080
```

Open Logfire at `http://localhost:8080`.

## First Access

On first install, the chart creates the `logfire-meta` organization and stores its frontend access token in a Kubernetes Secret:

```bash
kubectl -n logfire get secret logfire-meta-frontend-token \
  -o "jsonpath={.data.logfire-meta-frontend-token}" | base64 -d
```

Open the meta project with the token:

```text
http://localhost:8080/logfire-meta/logfire-meta#token=LOGFIRE_META_FRONTEND_TOKEN
```

After you have access, create an invite link from **Settings** > **Invite** and assign the **Admin** organization role.

## Send Test Data

Create a project and write token, then configure the SDK to use your local endpoint:

```python
import logfire

logfire.configure(
    token='YOUR_LOGFIRE_WRITE_TOKEN',
    advanced=logfire.AdvancedOptions(base_url='http://localhost:8080'),
)
logfire.info('Hello, {place}!', place='World')
```

## Cleanup

Delete the local cluster or uninstall the release:

```bash
helm -n logfire uninstall logfire
```
