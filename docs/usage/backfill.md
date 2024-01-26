# Backfilling data

When Logfire fails to send a log to the server, it will dump data to the disk to avoid data loss.

Logfire supports bulk loading data, either to import data from another system or to load data that
was dumped to disk.

To backfill data, you can use the `logfire backfill` command:

```bash
$ logfire backfill --help
```

By default `logfire backfill` will read from the default fallback file so if you are just trying to upload data after a network failure you can just run:

```bash
$ logfire backfill
```

## Bulk loading data

This same mechanism can be used to bulk load data, for example if you are importing it from another system.

First create a dump file:

```python
from datetime import datetime

from logfire.backfill import Log, PrepareBackfill, StartSpan

with PrepareBackfill('logfire_spans123.bin') as backfill:
    span = StartSpan(
        start_timestamp=datetime(2023, 1, 1, 0, 0, 0),
        span_name='session',
        msg_template='session {user_id=} {path=}',
        service_name='docs.pydantic.dev',
        log_attributes={'user_id': '123', 'path': '/test'},
    )
    child = StartSpan(
        start_timestamp=datetime(2023, 1, 1, 0, 0, 1),
        span_name='query',
        msg_template='ran db query',
        service_name='docs.pydantic.dev',
        log_attributes={'query': 'SELECT * FROM users'},
        parent=span,
    )
    backfill.write(
        Log(
            timestamp=datetime(2023, 1, 1, 0, 0, 2),
            msg_template='GET {path=}',
            level='info',
            service_name='docs.pydantic.dev',
            attributes={'path': '/test'},
        )
    )
    backfill.write(child.end(end_timestamp=datetime(2023, 1, 1, 0, 0, 3)))
    backfill.write(span.end(end_timestamp=datetime(2023, 1, 1, 0, 0, 4)))
```

This will create a `logfire_spans123.bin` file with the data.

Then use the `backfill` command line tool to load it:

```bash
$ logfire backfill --file logfire_spans123.bin
```
