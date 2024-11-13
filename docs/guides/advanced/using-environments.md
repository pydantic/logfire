If you set up Logfire according to the [getting started guide](../../index.md), you already have instrumented logfire in your applications
via the `logfire.configure()` function. If you find yourself wanting to distinguish between data sent in one environment (e.g. `dev` vs. `production`), it may be overkill to create a new project for each (more on how to decide this below).

Instead you can use the environments feature, which is a special kind of resource attribute applied to the whole payload received by Logfire.
This attribute says which environment the payload comes from.

You can set the environment for your project when calling `logfire.configure`:

```py title="main.py"
import logfire

logfire.configure(environment='dev')

logfire.info("Hi there!")
```

Under the hood, this sets the OTel [`deployment.environment.name`](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/).
Note that you can also set this via the `LOGFIRE_ENVIRONMENT` environment variable.

Once set, you will see your environment in the Logfire UI `all envs` dropdown, which appears
on the [Live View](../web-ui/live.md), [Dashboards](../web-ui/dashboards.md) and [Explore](../web-ui/explore.md) pages:

![Environments](../../images/guide/environments.png)

Note that by default there are system generated environments:

- `all envs`: Searches will include all spans with any environment set
- `not specified`: Searches will include all spans with no environment specified

Any environments you create via the SDK will appear below the system generated environments. When you select an environment,
all subsequent queries (e.g. on live view, dashboards or explore) will filter by that environment.

## Can I Create an Environment in the UI?
No, you cannot create or delete set environments via the UI, instead use the SDK.

## How do I delete an environment?
Once an environment has been configured and received by logfire, technically it’s available for
the length of the data retention period while that environment exists in the data.
You can however add new ones, and change the configuration of which data is assigned to which
environment name.

## Should I Use Environments or Projects?

Environments are more lightweight than projects. Projects give you the ability to assign specific
user groups and permissions levels (see this [organization structure diagram](docs/reference/organization-structure/) for details).
So if you need to allow different team members to view dev vs. prod traces, then projects would be a better fit.
