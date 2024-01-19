# [Flask][flask]

The [OpenTelemetry Instrumentation Flask][opentelemetry-flask] package can be used to instrument Flask.

## Install

Install `logfire` with the `flask` extra:

{{ install_logfire(extras=['flask']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
from flask import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor


logfire.configure()

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

@app.route("/")
def hello():
    return "Hello!"

if __name__ == "__main__":
    app.run(debug=True)
```

You can read more about the Flask OpenTelemetry package [here][opentelemetry-flask].

[flask]: https://flask.palletsprojects.com/en/2.0.x/
[opentelemetry-flask]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html
