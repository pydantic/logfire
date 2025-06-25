---
integration: otel
---

# Flask

The [`logfire.instrument_flask()`][logfire.Logfire.instrument_flask] method
will create a span for every request to your [Flask][flask] application.

## Install

Install `logfire` with the `flask` extra:

{{ install_logfire(extras=['flask']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
from flask import Flask


logfire.configure()

app = Flask(__name__)
logfire.instrument_flask(app)


@app.route("/")
def hello():
    return "Hello!"


if __name__ == "__main__":
    app.run(debug=True)
```

The keyword arguments of `logfire.instrument_flask()` are passed to the `FlaskInstrumentor().instrument_app()` method
of the OpenTelemetry Flask Instrumentation package, read more about it [here][opentelemetry-flask].

In case you are using Gunicorn to run your Flask application, you can [configure Logfire in Gunicorn](gunicorn.md) as well.

[flask]: https://flask.palletsprojects.com/en/2.0.x/
[opentelemetry-flask]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html
