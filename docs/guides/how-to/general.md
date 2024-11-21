Here are several pointers to other places in the docs, for general or frequent questions.


### Set a Service Name
To see your service names in the logfire UI, you just need to set the `service_name` parameter in
[`logfire.configure()`][logfire.configure(service_name)].

### Understanding the SQL Schema
With Logfire, you can use the UI to run arbitrary SQL queries against your trace and metric data to
analyze and investigate your system. For details of the data model, see
our [schema docs](../web-ui/explore.md#records-schema)

### Disable Logfire During Tests
Logfire makes it very easy to test the emitted logs and spans. See the [testing with logfire](../../advanced/testing) docs.
If you encounter difficulties disabling logfire during testing (and are using pytest),
ensure that in your conftest.py you set:

```py title="conftest.py"
import logfire

logfire.configure(send_to_logfire=False)
```

### Setting an Environment (e.g. dev, prod)
With Logfire you can distinguish which environment you are sending data to. See the [environments](../../advanced/environments.md) page.

### Querying Logs via API
Logfire provides a web API for programmatically running arbitrary SQL queries against the data in your Logfire projects.
See the [Query API docs](../../advanced/query-api.md)


### Use logfire Without Sending Data to a Server
To disable sending data to a server and just emit traces to stdout:
```py title="main.py"
import logfire

logfire.configure(send_to_logfire=False)
```

### Use an Alternative Backend

Logfire uses the OpenTelemetry standard. This means that you can configure the SDK to export to any
backend that supports OpenTelemetry. See our [alternative backends docs](../../advanced/alternative-backends.md)


### Combine Logs from Multiple Processes/Worker Machines Under One Span
The standard way to do this is with something called “context propagation”, which
we have a [docs page](../..reference/api/propagate.md) for.
