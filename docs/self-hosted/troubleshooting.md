# Troubleshooting Self Hosted

There are occasions when you need to troubleshoot the installation.  Since Logfire sends its own internal logs to the `logfire-meta` organisation, this is a good place to start.

## Accessing the Meta Organization

Logfire will send internal traces to a meta organisation that is created upon first install.   This meta organisation is helpful in troubleshooting any issues that might arise when running Logfire.

When the chart is first installed, a secret is created that allows system administrators access to the meta organisation via a special URL.

Follow these steps to access the meta organisation:

* Run the following command to get the meta token secret (changing `-n logfire` to your namespace or omitting it if it's default):
  ```
  kubectl get secret -n logfire logfire-meta-frontend-token -o "jsonpath={.data.logfire-meta-frontend-token}" | base64 -d
  ```
* With this and using your hostname, login to the meta organisation using the following link:
  ```
  https://<your-logfire-hostname>/logfire-meta/logfire-meta#token=<logfire-meta-frontend-token>
  ```

You should be able to see a stream of traces come through from each service.

To check for errors, use the following query filter:

```
level >= 'error'
```

### No Traces in Meta Organization

Logfire itself can have an issue sending traces to the `logfire-meta` organization.

If you don't see any traces this could mean that one of the services involved in ingest may not be configured correctly, or there is an issue with an external service, such as **PostgreSQL** or **Object Storage**.

One quick thing to check is the console logs involved in those services.  Here are a few steps you can take to hone in on the issue:

* Check that all pods are up and their status is `Running`:
 ```
 kubectl get pods -n logfire
 ```
* Check the console logs of the ingest pod for any errors ingesting new traces:
 ```
 kubectl logs -n logfire statefulset/logfire-ff-ingest
 kubectl logs -n logfire deployments/logfire-ff-ingest-api
 ```
* Check the console logs of the otel collector:
 ```
 kubectl logs -n logfire deployments/logfire-otel-collector
 ```
* Check the console logs of the query api:
 ```
 kubectl logs -n logfire deployments/logfire-ff-query-api
 ```
