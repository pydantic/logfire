# Testing with LogFire

You may want to check that your API is logging the data you expect, that spans correctly track the work they wrap, etc.
This can often be difficult, including with Python's built in logging and OpenTelemetry's SDKs.
Logfire makes it very easy to test the emitted logs and spans using the utilities in the `logfire.testing` module.
This is what Logfire uses internally to test itself as well.

Here's an example of a pytest fixture that lets you assert against all captured logs/spans:

```py
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


@pytest.fixture
def logfire_caplog() -> TestExporter:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        console_print='off',
        id_generator=IncrementalIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    return exporter


def test_observability(logfire_caplog: TestExporter) -> None:
    with pytest.raises(Exception):
        with logfire.span('a span!'):
            logfire.info('a log!')
            raise Exception('an exception!')

    # insert_assert(logfire_caplog.exported_spans_as_dict())
    assert logfire_caplog.exported_spans_as_dict() == [
        {
            'name': 'a log!',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'a log!',
                'logfire.msg': 'a log!',
                'code.filepath': 'test.py',
                'code.lineno': 123,
                'code.function': 'test_observability',
            },
        },
        {
            'name': 'a span!',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'test.py',
                'code.lineno': 123,
                'code.function': 'test_observability',
                'logfire.msg_template': 'a span!',
                'logfire.span_type': 'span',
                'logfire.msg': 'a span!',
            },
            'events': [
                {
                    'name': 'exception',
                    'timestamp': 3000000000,
                    'attributes': {
                        'exception.type': 'Exception',
                        'exception.message': 'an exception!',
                        'exception.stacktrace': 'Exception: an exception!',
                        'exception.escaped': 'True',
                        'exception.logfire.trace': '{"stacks": [{"exc_type": "Exception", "exc_value": "an exception!", "syntax_error": null, "is_cause": false, "frames": [{"filename": "test.py", "lineno": 123, "name": "test_observability", "line": "", "locals": null}]}]}',
                    },
                }
            ],
        },
    ]
```

Let's walk through the utilities we used.

## TestExporter

This is an OpenTelemetry SDK compatible span exporter that keeps exported spans in memory.
The `exported_spans_as_dict()` method lets you get a plain dict representation of the exported spans that you can easily assert against and get nice diffs from.
This method does some data massaging to make the output more readable and deterministic, e.g. replacing line numbers with `123` and file paths with just the filename.

## IncrementalIdGenerator

One of the most complicated things about comparing log output to expected results are sources of non-determinism.
For OpenTelemetry spans the two biggest ones are the span & trace IDs and timestamps.

The `IncrementalIdGenerator` generates sequentially increasing span and trace IDs so that test outputs are always the same.

## TimeGenerator

This class generates nanosecond timestamps that increment by 1s every time a timestamp is generated.

## logfire.configure

This is the same configuration function you'd use for production and where everything comes together.

Note that we specifically configure:

- `send_to_logfire=False` because we don't want to hit the actual production service
- `console_print='off'` to avoid adding bloat to stdout
- `id_generator=IncrementalIdGenerator()` to make the span IDs deterministic
- `ns_timestamp_generator=TimeGenerator()` to make the timestamps deterministic
- `processors=[SimpleSpanProcessor(exporter)]` to use our `TestExporter` to capture spans. We use `SimpleSpanProcessor` to export spans with no delay.

## insert_assert

This is a utility function provided by [devtools](https://github.com/samuelcolvin/python-devtools) that will automatically insert the output of the code it is called with into the test file when run via pytest. That is, if you comment that line out you'll see that the `assert logfire_caplog.exported_spans_as_dict() == [...]` line is replaced with the current output of `logfire_caplog.exported_spans_as_dict()`, which should be exactly the same given that our test is deterministic!
