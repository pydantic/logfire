---
hide:
- navigation
---

# Introducing Pydantic Logfire

From the team behind Pydantic, **Logfire** is an observability platform built on the same belief as our
open source library — that the most powerful tools can be easy to use.

What sets Logfire apart:

- **Simple and Powerful:** Logfire's dashboard is simple relative to the power it provides, ensuring your entire engineering team will actually use it.
- **Python-centric Insights:** From rich display of Python objects, to event-loop telemetry, to profiling Python code and database queries, Logfire gives you unparalleled visibility into your Python application's behavior.
- **SQL:** Query your data using standard SQL — all the control and (for many) nothing new to learn. Using SQL also means you can query your data with existing BI tools and database querying libraries.
- **OpenTelemetry:** Logfire is an opinionated wrapper around OpenTelemetry, allowing you to leverage existing tooling, infrastructure, and instrumentation for many common Python packages, and enabling support for virtually any language.
- **Pydantic Integration:** Understand the data flowing through your Pydantic models and get built-in analytics on validations.

Pydantic Logfire helps you instrument your applications with less code, less time, and better understanding.

## Find the needle in a _stacktrace_

![Logfire FastAPI screenshot](images/index/logfire-screenshot-fastapi-200.png)

We understand Python and its peculiarities. Pydantic Logfire was crafted by Python developers, for Python
developers, addressing the unique challenges and opportunities of the Python environment. It's not just about having
data; it's about having the *right* data, presented in ways that make sense for Python applications.

### In the Spirit of Python

- [**Simplicity and Power**](#simplicity): Emulating the Pydantic library's philosophy, Pydantic Logfire offers an
intuitive start for beginners while providing the depth experts desire. It's the same balance of ease, sophistication,
and productivity, reimagined for observability.
- **Born from Python and Pydantic**: As creators immersed in the Python open-source ecosystem, we've designed Pydantic
Logfire to deeply integrate with Python and Pydantic's nuances, delivering a more customized experience than generic
observability platforms.

### Elevating Data to Insights

- With [**deep Python integration**](#python), Pydantic Logfire automatically instruments your code for minimal manual
effort, provides exceptional insights into async code, offers detailed performance analytics, and displays Python
objects the same as the interpreter. For existing Pydantic users, it also delivers unparalleled insights into your usage
of Pydantic models.
- [**Structured Data and Direct SQL Access**](#sql) means you can use familiar tools like Pandas, SQLAlchemy, or `psql`
for querying, can integrate seamlessly with BI tools, and can even leverage AI for SQL generation, ensuring your Python
objects and structured data are query-ready. Using vanilla PostgreSQL as the querying language throughout the platform
ensures a consistent, powerful, and flexible querying experience.
- By [**harnessing OpenTelemetry**](#otel), Pydantic Logfire offers automatic instrumentation for popular Python packages,
enables cross-language data integration, and supports data export to any OpenTelemetry-compatible backend or proxy.

## Pydantic Logfire: The Observability Platform You Deserve

**Pydantic Logfire** isn't just another tool in the shed; it's the bespoke solution crafted by Python developers, for
Python developers, ensuring your development work is as smooth and efficient as Python itself.

From the smallest script to large-scale deployments, Pydantic Logfire is the observability solution you've been waiting
for.

---

### Simplicity and Power :rocket: {#simplicity}

**Pydantic Logfire** should be dead simple to start using, simply run:

```bash
pip install logfire # (1)!
logfire auth # (2)!
```

1. The **Pydantic Logfire** SDK can be installed from PyPI or Conda, [Learn more](guides/first_steps/index.md#install).
2. The SDK comes with a CLI for authentication and more, [Learn more](reference/cli.md).

Then in your code:

```py
import logfire
from datetime import date

logfire.configure()  # (1)!

logfire.info('Hello, {name}!', name='world')  # (2)!

with logfire.span('Asking the user their {question}', question='birthday'):  # (3)!
    user_input = input('When were you born [YYYY-mm-dd]? ')
    dob = date.fromisoformat(user_input)  # (4)!
    logfire.debug('{dob=} {age=!r}', dob=dob, age=date.today() - dob)  # (5)!
```

1. This should be called once before logging to initialize Logfire. If no project is configured for the current directory, an interactive prompt will walk you through creating a project.
2. This will log `Hello world!` with `info` level. `name='world'` will be stored as an attribute that can be queried with SQL.
3. Spans allow you to nest other Logfire calls, and also to measure how long code takes to run. They are the fundamental building block of traces!
4. Attempt to extract a date from the user input. If any exception is raised, the outer span will include the details of the exception.
5. This will log for example `dob=2000-01-01 age=datetime.timedelta(days=8838)` with `debug` level.

This might look similar to simple logging, but it's much more powerful — you get:

- structured data from your logs
- nested logs / traces to contextualize what you're viewing
- a custom-built platform to view your data, with no configuration required
- and more, like pretty display of Python objects — see below

!!! note
    If you have an existing app to instrument, you'll get the most value out of [configuring OTel integrations](#otel), before you start adding `logfire.*` calls to your code.

![Logfire hello world screenshot](images/index/logfire-screenshot-hello-world-age.png)

### Python and Pydantic insights :snake: {#python}

From rich display of Python objects to event-loop telemetry and profiling Python code, Pydantic Logfire can give you a clearer view into how your Python is running than any other observability tool.

Logfire also has an out-of-the-box Pydantic integration that lets you understand the data passing through your Pydantic models and get analytics on validations.

We can record Pydantic models directly:

```py
from datetime import date
import logfire
from pydantic import BaseModel

logfire.configure()

class User(BaseModel):
    name: str
    country_code: str
    dob: date

user = User(name='Anne', country_code='USA', dob='2000-01-01')
logfire.info('user processed: {user!r}', user=user)  # (1)!
```

1. This will show `user processed: User(name='Anne', country_code='US', dob=datetime.date(2000, 1, 1))`, but also allow you to see a "pretty" view of the model within the Logfire Platform.

![Logfire pydantic manual screenshot](images/index/logfire-screenshot-pydantic-manual.png)

Or we can record information about validations automatically:

```py
from datetime import date
import logfire
from pydantic import BaseModel

logfire.configure(pydantic_plugin=logfire.PydanticPlugin(record='all'))  # (1)!

class User(BaseModel):
    name: str
    country_code: str
    dob: date

User(name='Anne', country_code='USA', dob='2000-01-01')  # (2)!
User(name='Ben', country_code='USA', dob='2000-02-02')
User(name='Charlie', country_code='GBR', dob='1990-03-03')
```

1. This configuration means details about all Pydantic model validations will be recorded. You can also record details about validation failures only, or just metrics; see the [pydantic plugin docs][logfire.PydanticPlugin].
2. Since we've enabled the Pydantic Plugin, all Pydantic validations will be recorded in Logfire.

Learn more about the [Pydantic Plugin here](integrations/pydantic.md).

![Logfire pydantic plugin screenshot](images/index/logfire-screenshot-pydantic-plugin.png)

### OpenTelemetry under the hood :telescope: {#otel}

Because **Pydantic Logfire** is built on [OpenTelemetry](https://opentelemetry.io/), you can
use a wealth of existing tooling and infrastructure, including
[instrumentation for many common Python packages](https://opentelemetry-python-contrib.readthedocs.io/en/latest/index.html).

For example, we can instrument a simple FastAPI app with just 2 lines of code:

```py title="fastapi_example.py" hl_lines="8 9 10"
from datetime import date
import logfire
from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI()

logfire.configure()
logfire.instrument_fastapi(app)  # (1)!
# next, instrument your database connector, http library etc. and add the logging handler (2)


class User(BaseModel):
    name: str
    country_code: str
    dob: date


@app.post('/')
async def add_user(user: User):
    # we would store the user here
    return {'message': f'{user.name} added'}
```

1. In addition to [configuring logfire](reference/configuration.md) this line is generally all you need to instrument a FastAPI app with Logfire, the same applies to most other popular Python web frameworks.
2. The [integrations](integrations/index.md) page has more information on how to instrument other parts of your app.

We'll need the [FastAPI contrib package](integrations/fastapi.md), FastAPI itself and uvicorn installed to run this:

```bash
pip install 'logfire[fastapi]' fastapi uvicorn  # (1)!
uvicorn fastapi_example:app # (2)!
```

1. Install the `logfire` package with the `fastapi` extra, FastAPI, and uvicorn.
2. Run the FastAPI app with uvicorn.

This will give you information on the HTTP request, but also details of results from successful input validations:

![Logfire FastAPI 200 response screenshot](images/index/logfire-screenshot-fastapi-200.png)

And details of failed input validations:

![Logfire FastAPI 422 response screenshot](images/index/logfire-screenshot-fastapi-422.png)

### Structured Data and SQL :abacus: {#sql}

Query your data with pure, canonical Postgres SQL — all the control and (for many) nothing new to learn.
We even provide direct access to the underlying Postgres database, which means that you can query Logfire using any Postgres-compatible tools you like. This includes dashboard-building platforms like Superset, Grafana, and Google Looker Studio, but also **Pandas**, **SQLAlchemy**, or even `psql`.

One big advantage of using the most widely used SQL databases is that generative AI tools like ChatGPT are excellent at writing SQL for you.

Just include your Python objects in **Logfire** calls (lists, dict, dataclasses, Pydantic models, dataframes, and more),
and it'll end up as structured data in our platform ready to be queried.

For example, using data from the `User` model above, we could list users from the USA:

```sql
SELECT attributes->'result'->>'name' as name, age(attributes->'result'->>'dob') as age
FROM records
WHERE attributes->'result'->>'country_code' = 'USA'
```

![Logfire explore query screenshot](images/index/logfire-screenshot-explore-query.png)

You can also filter to show only traces related to users in the USA in the live view with

```SQL
attributes->'result'->>'country_code' = 'USA'
```

![Logfire search query screenshot](images/index/logfire-screenshot-search-query.png)
