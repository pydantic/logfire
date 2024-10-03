# Logfire + Flask + SQLAlchemy Example

This example is a simple Python financial calculator app which is instrumented with Logfire. If you spin up the server locally and interact with the calculator app, you'll be able to see traces come in automatically. The Logfire instrumentation is done with just a few lines of code in `main.py`.

## Run the project

Clone the repository, navigate to it, setup a virtual environment, and install the dependencies:

```bash
git clone https://github.com/pydantic/logfire.git
cd examples/python/flask-sqlalchemy
python -m venv venv
source venv/bin/activate
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
