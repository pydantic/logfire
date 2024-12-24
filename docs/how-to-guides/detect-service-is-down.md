For now, **Logfire** doesn't have a built-in way to detect if a service is down. In the sense that we don't ping
services via HTTP or any other protocol to check if they are up or down.

??? info "For now we don't have it, but..."
    If you would like to see this feature in **Logfire**, [let us know]!

    It's useful for us to understand the use cases and requirements for this feature.

However, you can create alerts to notify you when a log message is not received for a certain amount of time.
This can be used to detect if a service is down.

Let's say you have a [FastAPI application] that has a health check endpoint at `/health`.

```py
import logfire
from fastapi import FastAPI

logfire.configure(service_name="backend")
app = FastAPI()
logfire.instrument_fastapi(app)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

You probably have this endpoint because you have a mechanism that restarts the service if it's down.
In this case, you can use **Logfire** to send you an alert if the health check endpoint is not called
for a certain amount of time.

## Create the Alert

Go to [your alerts tab](https://logfire.pydantic.dev/-/redirect/latest-project/alerts/) and click on "New Alert".
Then add the following query to the alert:

```sql
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN 'backend is down'
        ELSE 'backend is up'
    END AS message
FROM
    records
WHERE
    service_name = 'backend' and span_name = 'GET /health';
```


This query will return `backend is down` if the `/health` endpoint on the `'backend'` service is not called.

On the "Alert Parameters", we want to be notified as soon as possible, so we should execute the query `"every minute"`,
include rows from `"the last minute"`, and notify us if `"the query's results change"`.

Then you need to set up a channel to send this notification, which can be a Slack channel or a webhook.
See more about it on the [alerts documentation](../guides/web-ui/alerts.md).

[FastAPI application]: ../integrations/web-frameworks/fastapi.md
[let us know]: ../help.md
