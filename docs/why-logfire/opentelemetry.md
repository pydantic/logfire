# OpenTelemetry under the hood :telescope:

Because **Pydantic Logfire** is built on [OpenTelemetry](https://opentelemetry.io/), you can
use a wealth of existing tooling and infrastructure, including
[instrumentation for many common Python packages](https://opentelemetry-python-contrib.readthedocs.io/en/latest/index.html). Logfire also supports cross-language data integration and data export to any OpenTelemetry-compatible backend or proxy.

For example, we can instrument a simple FastAPI app with just 2 lines of code:

```py title="main.py" hl_lines="8 9 10"
from datetime import date
import logfire
from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI()

logfire.configure()
logfire.instrument_fastapi(app)  # (1)!
# Here you'd instrument any other library that you use. (2)


class User(BaseModel):
    name: str
    country_code: str
    dob: date


@app.post('/')
async def add_user(user: User):
    # we would store the user here
    return {'message': f'{user.name} added'}
```

1. In addition to [configuring logfire](../reference/configuration.md) this line is all you need to instrument a FastAPI app with Logfire. The same applies to most other popular Python web frameworks.
2. The [integrations](../integrations/index.md) page has more information on how to instrument other parts of your app. Run the [inspect](../reference/cli.md#inspect-inspect) command for package suggestions.

We'll need the [FastAPI contrib package](../integrations/fastapi.md), FastAPI itself and uvicorn installed to run this:

```bash
pip install 'logfire[fastapi]' fastapi uvicorn  # (1)!
uvicorn fastapi_example:app # (2)!
```

1. Install the `logfire` package with the `fastapi` extra, FastAPI, and uvicorn.
2. Run the FastAPI app with uvicorn.

This will give you information on the HTTP request and details of results from successful input validations:

![Logfire FastAPI 200 response screenshot](../images/index/logfire-screenshot-fastapi-200.png)

And, importantly, details of failed input validations:

![Logfire FastAPI 422 response screenshot](../images/index/logfire-screenshot-fastapi-422.png)

In the example above, we can see the FastAPI arguments failing (`user` is null when it should always be populated). This demonstrates type-checking from Pydantic used out-of-the-box in FastAPI.
