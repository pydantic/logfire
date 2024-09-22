<!-- ---
hide:
- navigation
--- -->

# Get Started

<!-- - [ ] Create an account
- [ ] Set up your first project
- [ ] Install Logfire SDK
- [ ] Authenticate your local environment
- [ ] Instrument your code

=== "Development"
    Dev tab
=== "Production"
    Production tab -->

## Logfire platform
1. [Log into Logfire :material-open-in-new:](https://logfire.pydantic.dev/login){:target="_blank"}
2. Follow the prompts to create your account
3. From your Organisation, click `New project` and create your first project


!!! note
    The first time you use **Logfire** in a new environment, you'll need to set up a project. A **Logfire** project is a namespace for organizing your data. All data sent to **Logfire** must be associated with a project.


## Install SDK {#install}

To install the latest version of **Logfire**, run:

{{ install_logfire() }}

## Authenticate

Authenticate your local environment with **Logfire** by running:

```bash
logfire auth
```

!!! note
    Upon successful authentication, credentials are stored in `~/.logfire/default.toml`.

## Basic Usage

To use **Logfire**, it's simple as:

```py
import logfire

logfire.configure()  # (1)!
logfire.info('Hello, {name}!', name='world')  # (2)!
```

1. The `configure()` should be called once before logging to initialize **Logfire**.
2. This will log `Hello world!` with `info` level.

!!! note

    Other [log levels][logfire.Logfire] are also available to use, including `trace`, `debug`, `notice`, `warn`,
    `error`, and `fatal`.



??? success "You can also create a project via CLI..."
    Check the [SDK CLI documentation](reference/cli.md#create-projects-new) for more information on how to create a project via CLI.

Once you've created a project, you should see:

```bash
Logfire project URL: https://logfire.pydantic.dev/dmontagu/my-project
19:52:12.323 Hello, world!
```

**Logfire** will always start by displaying the URL of your project, and (with default configuration) will also provide a
basic display in the terminal of the logs you are sending to Logfire.

![Hello world screenshot](images/logfire-screenshot-first-steps-hello-world.png)

## Tracing with Spans

Spans let you add context to your logs and measure code execution time. Multiple spans combine to form a trace,
providing a complete picture of an operation's journey through your system.

```py
from pathlib import Path
import logfire

cwd = Path.cwd()
total_size = 0

logfire.configure()

with logfire.span('counting size of {cwd=}', cwd=cwd):
    for path in cwd.iterdir():
        if path.is_file():
            with logfire.span('reading {file}', file=path):
                total_size += len(path.read_bytes())

    logfire.info('total size of {cwd} is {size} bytes', cwd=cwd, size=total_size)
```

In this example:

1. The outer span measures the time to count the total size of files in the current directory (`cwd`).
2. Inner spans measure the time to read each individual file.
3. Finally, the total size is logged.

![Counting size of loaded files screenshot](images/logfire-screenshot-first-steps-load-files.png)

By instrumenting your code with traces and spans, you can see how long operations take, identify bottlenecks,
and get a high-level view of request flows in your system — all invaluable for maintaining the performance and
reliability of your applications.

[conda]: https://conda.io/projects/conda/en/latest/user-guide/install/index.html


-----

**Pydantic Logfire** should be dead simple to start using, simply run:


Then in your code:

```py
import logfire
from datetime import date

logfire.configure()  # (1)!

logfire.info('Hello, {name}!', name='world')  # (2)!

with logfire.span('Asking the user for their {question}', question='birthday'):  # (3)!
    user_input = input('When were you born [YYYY-mm-dd]? ')
    dob = date.fromisoformat(user_input)  # (4)!
    logfire.debug('{dob=} {age=!r}', dob=dob, age=date.today() - dob)  # (5)!
```

1. This should be called once before logging to initialize Logfire. If no project is configured for the current directory, an interactive prompt will walk you through creating a project.
2. This will log `Hello world!` with `info` level. `name='world'` will be stored as an attribute that can be queried with SQL.
3. Spans allow you to nest other Logfire calls, and also to measure how long code takes to run. They are the fundamental building block of traces!
4. Attempt to extract a date from the user input. If any exception is raised, the outer span will include the details of the exception.
5. This will log for example `dob=2000-01-01 age=datetime.timedelta(days=8838)` with `debug` level.


!!! note
    If you have an existing app to instrument, you'll get the most value out of [configuring OTel integrations](#otel), before you start adding `logfire.*` calls to your code.

---
