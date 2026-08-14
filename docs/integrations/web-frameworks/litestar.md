---
title: "Instrument Litestar: see every request your app handles"
description: "Add Logfire to a Litestar app and record routes, response statuses, timing, and errors."
integration: otel
---
# Litestar

See every request your [Litestar][litestar] app handles as a **trace** (the full journey of one
request, made of nested **spans**, where each span is one operation with a start and duration).
Logfire records the matched route, response status, timing, and errors.

## What you'll capture

- Each request as a span, including its status and duration
- Canonical route templates, so requests to `/users/1` and `/users/2` group under `/users/{user_id}`
- HTTP failures marked with warning or error severity based on the response status

{{ before_you_start() }}

## Installation

Install Logfire with the `litestar` extra:

{{ install_logfire(extras=['litestar']) }}

## Start recording requests

Pass the plugin returned by [`logfire.instrument_litestar()`][logfire.Logfire.instrument_litestar]
to Litestar when you construct your app:

```py title="main.py" hl_lines="8 18" skip-run="true" skip-reason="server-start"
from typing import Annotated

from litestar import Litestar, get
from litestar.params import Parameter

import logfire

logfire.configure()


@get('/hello/{name:str}')
async def hello(name: Annotated[str, Parameter()]) -> dict[str, str]:
    return {'message': f'Hello, {name}!'}


app = Litestar(
    route_handlers=[hello],
    plugins=[logfire.instrument_litestar()],
)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app)
```

Install Uvicorn, the server used by this example, and start the app:

```bash
pip install uvicorn
python main.py
```

## Verify it worked

Open [http://localhost:8000/hello/world](http://localhost:8000/hello/world), then open the **Live**
view in the [Logfire web app](https://logfire.pydantic.dev/). You should see a
`GET /hello/{name}` span. Open it to inspect the response status and duration.

## Troubleshooting

- **No request spans appear:** call `logfire.configure()` before `logfire.instrument_litestar()`.
- **The app starts but remains uninstrumented:** put the returned plugin in Litestar's `plugins`
  list; `instrument_litestar()` does not modify an existing app.
- **Low-level send and receive spans are missing:** these noisy spans are disabled by default. Pass
  `record_send_receive=True` when you need them for debugging.

## Advanced configuration

Pass Litestar OpenTelemetry configuration options directly to `instrument_litestar()`.

!!! warning "Captured headers are sent to Logfire"
    `capture_headers=True` captures every request and response header. Logfire
    [scrubs sensitive values by default](../../how-to-guides/scrubbing.md), but you should still review the headers
    your app uses before enabling it.

## Reference

- API reference: [`logfire.instrument_litestar()`][logfire.Logfire.instrument_litestar]
- Framework: [Litestar][litestar]

[litestar]: https://litestar.dev/
