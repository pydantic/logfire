# Local Quickstart

This guide provides a fast path for setting up a local Logfire instance on Kubernetes to test, prototype, and evaluate the product.

For a production setup, including detailed configuration and prerequisites, please refer to our In-Depth [Installation Guide](./installation.md).

---

## Prerequisites

Before deploying, you will need the following:

- A Logfire Access Key, you'll need to get in contact with [sales@pydantic.dev](mailto:sales@pydantic.dev) to get one.
- A local Kubernetes cluster, we will be using [Kind](https://kind.sigs.k8s.io/) in this example.
- [Helm](https://helm.sh) CLI installed.
- (Optional) [Tilt](https://tilt.dev/), as we will provide an optional convenience `Tiltfile` to automate the setup.

## Setup

You need to create a local Kubernetes cluster:

```bash
kind create cluster
```

The [Logfire Helm Chart](https://github.com/pydantic/logfire-helm-chart) repository needs to be added to Helm:

```bash
helm repo add pydantic https://charts.pydantic.dev/
helm repo update
```

Once the Kubernetes cluster is up and running you need to setup your Logfire Access key as a Kubernetes Secret to be able to pull the images, we'll call that secret `regcred`.

You'll need to replace `<YOUR_EMAIL>` with the email and `<YOUR_SECRET>` with the secret file provided to you by the Pydantic Team:

```bash
kubectl create secret docker-registry regcred \
  --docker-server=us-docker.pkg.dev \
  --docker-username=_json_key \
  --docker-password="$(cat <YOUR_SECRET>)" \
  --docker-email=<YOUR_EMAIL>
```

### Installing Logfire

You can now install Logfire using the Helm chart, with the development dependencies enabled.
!!! warning
    These development services are not suitable for production use. They lack persistence, backup, and security configurations.

Here is a minimal command to run Logfire in development mode, you can customize `adminEmail` if you want to access Logfire's self telemetry, but it's not required:

```bash
helm install logfire pydantic/logfire \
  --set=adminEmail=my-awesome-email@example.com \
  --set="imagePullSecrets[0]=regcred" \
  --set=dev.deployPostgres=true \
  --set=dev.deployMinio=true \
  --set=dev.deployMaildev=true \
  --set=objectStore.uri=s3://logfire \
  --set=objectStore.env.AWS_ACCESS_KEY_ID=logfire-minio \
  --set=objectStore.env.AWS_SECRET_ACCESS_KEY=logfire-minio \
  --set=objectStore.env.AWS_ENDPOINT=http://logfire-minio:9000 \
  --set=objectStore.env.AWS_ALLOW_HTTP=true \
  --set=ingress.hostname=localhost:8080
```

You can refer to the [Logfire Helm Chart](https://github.com/pydantic/logfire-helm-chart) documentation to check all the supported configurations.
Also check our [full installation guide](./installation.md) for a complete checklist and a detailed example `values.yaml` to get you started on your production setup.

## Setup with Tilt (Optional)

If you are a [Tilt](https://tilt.dev/) user, you can use this `Tiltfile` to automate the Logfire setup:

```python title="Tiltfile"
load('ext://secret', 'secret_yaml_registry')
load('ext://helm_resource', 'helm_resource', 'helm_repo')


update_settings ( max_parallel_updates = 3 , k8s_upsert_timeout_secs = 600 , suppress_unused_image_warnings = None )
k8s_yaml(secret_yaml_registry("regcred", flags_dict = {
    'docker-server': 'us-docker.pkg.dev',
    'docker-username': '_json_key',
    'docker-email': os.getenv('LOGFIRE_EMAIL'),
    'docker-password': read_file(os.getenv('LOGFIRE_KEY_PATH'))
}))

helm_repo('pydantic', 'https://charts.pydantic.dev/')
helm_resource('logfire', 'pydantic/logfire', flags=[
  '--set=adminEmail=' + os.getenv('LOGFIRE_ADMIN_EMAIL'),
  '--set=imagePullSecrets[0]=regcred',
  '--set=dev.deployPostgres=true',
  '--set=dev.deployMinio=true',
  '--set=dev.deployMaildev=true',
  '--set=objectStore.uri=s3://logfire',
  '--set=objectStore.env.AWS_ACCESS_KEY_ID=logfire-minio',
  '--set=objectStore.env.AWS_SECRET_ACCESS_KEY=logfire-minio',
  '--set=objectStore.env.AWS_ENDPOINT=http://logfire-minio:9000',
  '--set=objectStore.env.AWS_ALLOW_HTTP=true',
  '--set=ingress.hostname=localhost:8080',
  ],
  links=[link('http://localhost:1080', 'maildev')],
)
k8s_resource(
  workload='logfire',
  port_forwards=[
    port_forward(8080, 8080, name='logfire'),
  ],
  extra_pod_selectors=[
    {'app.kubernetes.io/component': 'logfire-service'},
  ],
discovery_strategy='selectors-only',
)

local_resource(
  'maildev-portforward',
  serve_cmd='kubectl port-forward svc/logfire-maildev 1080:1080',
  deps=['logfire'],
  allow_parallel=True,
)
```

You just need to create a local Kubernetes cluster, for example:

```bash
kind create cluster
```

and running Tilt, configuring the few required parameters using the environment variables:

```bash
LOGFIRE_EMAIL=<LOGFIRE_EMAIL> \
LOGFIRE_KEY_PATH="$(pwd)/key.json" \
LOGFIRE_ADMIN_EMAIL=<ADMIN_EMAIL> \
tilt up
```

## Using Logfire

To access your local Logfire installation from you host you'll need to port forward `logfire-service`:

```bash
kubectl port-forward service/logfire-service 8080:8080
```

and `logfire-maildev`, for receiving emails and enabling user signups:

```bash
kubectl port-forward service/logfire-maildev 1080:1080
```

You are now ready to use Logfire with your browser of choice navigating to `http://localhost:8080/`

You can access the emails for signin up going to `http://localhost:1080`.

After creating your user, your project and your write token, you can start sending data to Logfire in the same fashion as always:

```python
import logfire

logfire.configure(
  advanced=logfire.AdvancedOptions(base_url='http://localhost:8080'),
  token='__YOUR_LOGFIRE_WRITE_TOKEN__'
)
logfire.info('Hello, {place}!', place='World')
```

## Cleanup

In order to cleanup your local environment you can just delete the k8s cluster:

```bash
kind delete cluster
```

## Troubleshooting and support

If you encounter issues, we recommend first consulting the [Troubleshooting](./troubleshooting.md) section.

If your issue persists, please open a detailed issue on [Github](https://github.com/pydantic/logfire-helm-chart/issues), including:

* Chart version
* Kubernetes version
* A sanitized copy of your ```values.yaml```
* Relevant logs or error messages

For commercial or enterprise support, contact [our sales team](mailto:sales@pydantic.dev).
