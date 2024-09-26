# Pydantic Logfire — Uncomplicated Observability

[![CI](https://github.com/pydantic/logfire/actions/workflows/main.yml/badge.svg?event=push)](https://github.com/pydantic/logfire/actions?query=event%3Apush+branch%3Amain+workflow%3ACI)
[![codecov](https://codecov.io/gh/pydantic/logfire/graph/badge.svg?token=735CNGCGFD)](https://codecov.io/gh/pydantic/logfire)
[![pypi](https://img.shields.io/pypi/v/logfire.svg)](https://pypi.python.org/pypi/logfire)
[![license](https://img.shields.io/github/license/pydantic/logfire.svg)](https://github.com/pydantic/logfire/blob/main/LICENSE)
[![versions](https://img.shields.io/pypi/pyversions/logfire.svg)](https://github.com/pydantic/logfire)

From the team behind Pydantic, **Logfire** is an observability platform built on the same belief as our
open source library — that the most powerful tools can be easy to use.

What sets Logfire apart:

- **Simple and Powerful:** Logfire's dashboard is simple relative to the power it provides, ensuring your entire engineering team will actually use it.
- **Python-centric Insights:** From rich display of Python objects, to event-loop telemetry, to profiling Python code and database queries, Logfire gives you unparalleled visibility into your Python application's behavior.
- **SQL:** Query your data using standard SQL — all the control and (for many) nothing new to learn. Using SQL also means you can query your data with existing BI tools and database querying libraries.
- **OpenTelemetry:** Logfire is an opinionated wrapper around OpenTelemetry, allowing you to leverage existing tooling, infrastructure, and instrumentation for many common Python packages, and enabling support for virtually any language.
- **Pydantic Integration:** Understand the data flowing through your Pydantic models and get built-in analytics on validations.

See the [documentation](https://logfire.pydantic.dev/docs/) for more information.

**Feel free to report issues and ask any questions about Logfire in this repository!**

This repo contains the Python SDK for `logfire` and documentation; the server application for recording and displaying data is closed source.

## Using Logfire

This is a very brief overview of how to use Logfire, the [documentation](https://logfire.pydantic.dev/docs/) has much more detail.

### Install

```bash
pip install logfire
```
[_(learn more)_](https://logfire.pydantic.dev/docs/guides/first_steps/#install)

## Authenticate

```bash
logfire auth
```
[_(learn more)_](https://logfire.pydantic.dev/docs/guides/first_steps/#authentication)

### Manual tracing

Here's a simple manual tracing (aka logging) example:

```python
import logfire
from datetime import date

logfire.info('Hello, {name}!', name='world')

with logfire.span('Asking the user their {question}', question='age'):
    user_input = input('How old are you [YYYY-mm-dd]? ')
    dob = date.fromisoformat(user_input)
    logfire.debug('{dob=} {age=!r}', dob=dob, age=date.today() - dob)
```
[_(learn more)_](https://logfire.pydantic.dev/docs/guides/onboarding-checklist/add-manual-tracing/)

### Integration

Or you can also avoid manual instrumentation and instead integrate with [lots of popular packages](https://logfire.pydantic.dev/docs/integrations/), here's an example of integrating with FastAPI:

```py
import logfire
from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI()

logfire.configure()
logfire.instrument_fastapi(app)
# next, instrument your database connector, http library etc. and add the logging handler

class User(BaseModel):
    name: str
    country_code: str

@app.post('/')
async def add_user(user: User):
    # we would store the user here
    return {'message': f'{user.name} added'}
```
[_(learn more)_](https://logfire.pydantic.dev/docs/integrations/fastapi/)

Logfire gives you a view into how your code is running like this:

![Logfire screenshot](https://logfire.pydantic.dev/docs/images/index/logfire-screenshot-fastapi-200.png)

## Contributing

We'd love anyone interested to contribute to the Logfire SDK and documentation, see the [contributing guide](https://github.com/pydantic/logfire/blob/main/CONTRIBUTING.md).

## Reporting a Security Vulnerability

See our [security policy](https://github.com/pydantic/logfire/security).
