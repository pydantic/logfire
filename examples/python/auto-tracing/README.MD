# Logfire Auto-Tracing Example on Python

This example is a simple Python financial calculator app which is instrumented with the [auto-tracing method](../../../docs/guides/onboarding_checklist/add_auto_tracing.md). If you spin up the server locally and interact with the calculator app, you'll be able to see traces come in automatically.

## Run the project

To run the example locally, you need
1. A Logfire account
2. This project cloned locally
3. A recent version of Python installed.

If you don't have a Logfire account, create a free one [in Logfire](https://logfire.pydantic.dev/).


### Local setup

Clone the repository:

```bash
git clone https://github.com/pydantic/logfire.git
```

`cd` into the example directory and install:

```bash
cd examples/python/auto-tracing
```

Create a virtual environment in this repo

```bash
python -m venv venv
```

Activate your virtual environment

```bash
source venv/bin/activate
```

Install the app requirements

```bash
pip install -r requirements.txt
```

Install Logfire

```bash
pip install logfire
```

Authenticate Logfire

```bash
logfire auth
```


### Run your app locally

Run the `main.py` file:

```bash
python main.py
```

---

Now you should see

- Python app running locally at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- Logfire app running live at https://logfire.pydantic.dev/<my-org>/<my-project>

In order to see traces arrive in the Logfire app, interact with the local calculator app (click around, enter values into the fields, click calculate)
