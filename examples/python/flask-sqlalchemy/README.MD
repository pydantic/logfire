# Logfire + Flask + SQLAlchemy Example

This example is a simple Python financial calculator app which is instrumented with Logfire. If you spin up the server locally and interact with the calculator app, you'll be able to see traces come in automatically. The instrumentation is done with just these lines of code at the start of `main.py`:

```python
import logfire

logfire.install_auto_tracing(modules=['app'], min_duration=0)

from app import app, db  # needs to be imported after install_auto_tracing

logfire.configure()
logfire.instrument_sqlalchemy()
logfire.instrument_flask(app)
```

## Run the project

Clone the repository:

```bash
git clone https://github.com/pydantic/logfire.git
```

`cd` into the example directory and install:

```bash
cd examples/python/flask-sqlalchemy
```

Create a virtual environment in this repo

```bash
python -m venv venv
```

Activate your virtual environment

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install 'logfire[sqlalchemy,flask]' flask-sqlalchemy
```

If you don't have a Logfire account, create a free one [in Logfire](https://logfire.pydantic.dev/). Then authenticate Logfire locally:

```bash
logfire auth
```

Run the `main.py` file:

```bash
python main.py
```

Now you should see

- Python app running locally at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- Logfire app running live at `https://logfire.pydantic.dev/<my-org>/<my-project>`

In order to see traces arrive in the Logfire app, interact with the local calculator app (click around, enter values into the fields, click calculate)
