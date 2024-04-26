# Logfire — Uncomplicated Observability

[![CI](https://github.com/pydantic/logfire/actions/workflows/main.yml/badge.svg?event=push)](https://github.com/pydantic/logfire/actions?query=event%3Apush+branch%3Amain+workflow%3ACI)
[![pypi](https://img.shields.io/pypi/v/logfire.svg)](https://pypi.python.org/pypi/logfire)
[![license](https://img.shields.io/github/license/pydantic/logfire.svg)](https://github.com/pydantic/logfire/blob/main/LICENSE)
[![downloads](https://static.pepy.tech/badge/logfire/month)](https://pepy.tech/project/logfire)
[![versions](https://img.shields.io/pypi/pyversions/logfire.svg)](https://github.com/pydantic/logfire)

Logging and more like you always hoped it would be.

See the [documentation](https://docs.pydantic.dev/logfire/) for more information.

**Feel free to report issues and ask questions about `logfire` in this repository!**

This repo contains the Python SDK for `logfire` and documentation, the server application for recording and displaying data is closed source.

## Installation

```bash
pip install logfire
```
[_(learn more)_](https://docs.pydantic.dev/logfire/guides/first_steps/?h=install#install)

## Usage

Very simple logging/tracing example:

```python
import logfire
from datetime import date

logfire.info('Hello, {name}!', name='world')

with logfire.span('Asking the user their {question}', question='age'):
    user_input = input('How old are you [YYYY-mm-dd]? ')
    dob = date.fromisoformat(user_input)
    logfire.debug('{dob=} {age=!r}', dob=dob, age=date.today() - dob)
```
[_(learn more)_](https://docs.pydantic.dev/logfire/guides/onboarding_checklist/03_add_manual_tracing/)

Or you can avoid manual instrumentation and instead integrate with [lots of popular packages](https://github.com/samuelcolvin?tab=repositories), here's an example of integrating with FastAPI:

```py
from datetime import date
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
    dob: date


@app.post('/')
async def add_user(user: User):
    # we would store the user here
    return {'message': f'{user.name} added'}
```
[_(learn more)_](https://docs.pydantic.dev/logfire/integrations/fastapi/)

## Contributing

We'd love anyone interested to contribute to the Logfire SDK and documentation, see the [contributing guide](./CONTRIBUTING.md).

## Reporting a Security Vulnerability

See our [security policy](https://github.com/pydantic/.github).
