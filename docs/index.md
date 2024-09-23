<!-- ---
hide:
- navigation
--- -->

# Get Started

Follow the steps below to

1. [Set up Logfire](#logfire)
2. [Install the SDK](#sdk)
3. [Instrument your project](#instrument)


## Set up Logfire {#logfire}
1. [Log into Logfire :material-open-in-new:](https://logfire.pydantic.dev/login){:target="_blank"}
2. Follow the prompts to create your account
3. From your Organisation, click **New project** to create your first project

![Counting size of loaded files screenshot](images/logfire-screenshot-first-steps-first-project.png)

!!! info
    The first time you use **Logfire** in a new environment, you'll need to set up a project. A **Logfire** project is a namespace for organizing your data. All data sent to **Logfire** must be associated with a project.

??? tip "You can also create a project via CLI..."
    Check the [SDK CLI documentation](reference/cli.md#create-projects-new) for more information on how to create a project via CLI.

## Install the SDK {#sdk}

1. Install the latest version of the **Logfire** SDK:

{{ install_logfire() }}

2. Once installed, try it out!

```bash
logfire -h
```

3. Next, authenticate your local environment:

```bash
logfire auth
```

!!! info
    Upon successful authentication, credentials are stored in `~/.logfire/default.toml`.

## Instrument your project {#instrument}
=== ":material-cog-outline: Development"
    !!! tip "Development setup"
        During development, we recommend using the CLI to configure Logfire. You can also use a write token.

    1. Set project

    ```bash
    logfire projects use <first-project>
    ```

    2. Write your first logs

    ```py
    import logfire

    logfire.configure()  # (1)!
    logfire.info('Hello, {name}!', name='world')  # (2)!
    ```

    1. The `configure()` method should be called once before logging to initialize **Logfire**.
    2. This will log `Hello world!` with `info` level.

    !!! info
        Other [log levels][logfire.Logfire] are also available to use, including `trace`, `debug`, `notice`, `warn`,
        `error`, and `fatal`.


    3. See your logs in the **Live** view

    ![Hello world screenshot](images/logfire-screenshot-first-steps-hello-world.png)


=== ":material-cloud-outline: Production"
    !!! tip "Production setup"
        In production, we recommend you provide your write token to the Logfire SDK via environment variables.

    1. Generate a new write token

        - Go to Project :material-chevron-right: Settings :material-chevron-right: Write Tokens
        - Follow the prompts to create a new token


    2. Configure your **Logfire** environment

    ```bash
    LOGFIRE_TOKEN=<your-write-token>
    ```

    3. Write your first logs

    ```py
    import logfire

    logfire.configure()  # (1)!
    logfire.info('Hello, {name}!', name='world')  # (2)!
    ```

    1. The `configure()` method should be called once before logging to initialize **Logfire**.
    2. This will log `Hello world!` with `info` level.

    !!! info
        Other [log levels][logfire.Logfire] are also available to use, including `trace`, `debug`, `notice`, `warn`,
        `error`, and `fatal`.

    4. See your logs in the **Live** view

    ![Hello world screenshot](images/logfire-screenshot-first-steps-hello-world.png)


<!-- ## Basic Usage

Once you've created a project, you should see:

```bash
Logfire project URL: https://logfire.pydantic.dev/dmontagu/my-project
19:52:12.323 Hello, world!
```

**Logfire** will always start by displaying the URL of your project, and (with default configuration) will also provide a
basic display in the terminal of the logs you are sending to Logfire.

![Hello world screenshot](images/logfire-screenshot-first-steps-hello-world.png)




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

--- -->
