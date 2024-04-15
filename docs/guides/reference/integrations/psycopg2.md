# Psycopg2

The [OpenTelemetry Instrumentation Psycopg2][opentelemetry-psycopg2] package can be used to instrument [Psycopg2][psycopg2].

## Installation

Install `logfire` with the `psycopg2` extra:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

<!-- TODO: Make sure this works. -->

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor


logfire.configure()
Psycopg2Instrumentor().instrument()

cnx = psycopg2.connect(database='database')

cursor = cnx.cursor()
cursor.execute("SELECT * FROM Table")

cnx.close()
```

You can read more about the Psycopg2 OpenTelemetry package [here][opentelemetry-psycopg2].

!!! bug
    A bug occurs when `opentelemetry-instrumentation-psycopg2` is used with `psycopg2-binary` instead of `psycopg2`.
    More details on the issue can be found [here][psycopg2-binary-issue].

    A workaround is to include `skip_dep_check` in `instrument` method:

    ```py
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Psycopg2Instrumentor().instrument(skip_dep_check=True)
    ```

[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[psycopg2]: https://www.psycopg.org/
[psycopg2-binary-issue]: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/610
