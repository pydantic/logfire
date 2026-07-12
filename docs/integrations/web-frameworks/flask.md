---
title: "Instrument Flask: see every request your app handles"
description: "Add a few lines to your Flask app and see every request in Logfire: the route, timing, the response status, and any errors."
integration: otel
---
# Flask

See every request your [Flask][flask] app handles (the route, how long it took, the response status,
and any errors) as a **trace** (the full journey of one request, made of nested **spans**, where each
span is one unit of work with a name, a start, and a duration) in Logfire.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The matched route and method
- Any errors raised while handling the request

{{ before_you_start() }}

## Installation

Install `logfire` with the `flask` extra:

{{ install_logfire(extras=['flask']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_flask()`][logfire.Logfire.instrument_flask] to record every request.

```py title="main.py" hl_lines="5 8" skip-run="true" skip-reason="server-start"
from flask import Flask

import logfire

logfire.configure()

app = Flask(__name__)
logfire.instrument_flask(app)


@app.route('/')
def hello():
    return 'Hello!'


if __name__ == '__main__':
    app.run(debug=True)
```

Run it with `python main.py`.

## Verify it worked

With the app running, open [http://localhost:5000/](http://localhost:5000/) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
matched route, and the response status.

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_flask()`.** Configure the connection
  first, then instrument the app.
- **You call `instrument_flask(app)` exactly once**, on the same `app` object you serve.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after a route is hit; reload the URL above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_flask()`][logfire.Logfire.instrument_flask] accepts additional keyword arguments
and passes them to the OpenTelemetry `FlaskInstrumentor().instrument_app()` method. See
[their documentation][opentelemetry-flask] for the full list.

### Running under Gunicorn

If you run your Flask application with Gunicorn, you can also
[configure Logfire in Gunicorn](gunicorn.md).

## Reference

- API reference: [`logfire.instrument_flask()`][logfire.Logfire.instrument_flask]
- Underlying OpenTelemetry package: [Flask instrumentation][opentelemetry-flask]

[flask]: https://flask.palletsprojects.com/en/2.0.x/
[opentelemetry-flask]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html
