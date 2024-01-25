# Testing with Logfire

You may want to check that your API is logging the data you expect, that spans correctly track the work they wrap, etc.
This can often be difficult, including with Python's built in logging and OpenTelemetry's SDKs.

Logfire makes it very easy to test the emitted logs and spans using the utilities in the
[`logfire.testing`][logfire.testing] module.
This is what Logfire uses internally to test itself as well.

## `logfire_test_exporter` fixture

This has two attributes `exporter` and `metrics_reader`.

### `exporter`

This is an instance of [`TestExporter`][logfire.testing.TestExporter] and is an OpenTelemetry SDK compatible
span exporter that keeps exported spans in memory.

The [`exporter.exported_spans_as_dict()`][logfire.testing.TestExporter.exported_spans_as_dict] method lets you get
a plain dict representation of the exported spans that you can easily assert against and get nice diffs from.
This method does some data massaging to make the output more readable and deterministic, e.g. replacing line
numbers with `123` and file paths with just the filename.

```py
import pytest

import logfire
from logfire.testing import  LogfireTestExporter


def test_observability(logfire_test_exporter: LogfireTestExporter) -> None:
    with pytest.raises(Exception):
        with logfire.span('a span!'):
            logfire.info('a log!')
            raise Exception('an exception!')

    exporter = logfire_test_exporter.exporter

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'a log!',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'info', 'logfire.level_num': 9,
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

You can access exported spans by `exporter.exported_spans`.

```py
import logfire
from logfire.testing import LogfireTestExporter


def test_exported_spans(logfire_test_exporter: LogfireTestExporter) -> None:
    with logfire.span('a span!'):
        logfire.info('a log!')

    exporter = logfire_test_exporter.exporter

    expected_span_names = ['a span! (pending)', 'a log!', 'a span!']
    span_names = [span.name for span in exporter.exported_spans]

    assert span_names == expected_span_names
```

You can call `exporter.clear()` to reset the captured spans in a test.

```py
import logfire
from logfire.testing import LogfireTestExporter


def test_reset_exported_spans(logfire_test_exporter: LogfireTestExporter) -> None:
    exporter = logfire_test_exporter.exporter

    assert len(exporter.exported_spans) == 0

    logfire.info('First log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'First log!'

    logfire.info('Second log!')
    assert len(exporter.exported_spans) == 2
    assert exporter.exported_spans[1].name == 'Second log!'

    exporter.clear()
    assert len(exporter.exported_spans) == 0

    logfire.info('Third log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'Third log!'
```

### `metrics_reader`
This is an instance of [`InMemoryMetricReader`](https://opentelemetry-python.readthedocs.io/en/latest/sdk/metrics.export.html#opentelemetry.sdk.metrics.export.InMemoryMetricReader)
which reads metrics into memory.

```py
import json
from typing import cast

from opentelemetry.sdk.metrics.export import MetricsData

from logfire.testing import LogfireTestExporter


def test_system_metrics_collection(logfire_test_exporter: LogfireTestExporter) -> None:
    exported_metrics = json.loads(cast(MetricsData, logfire_test_exporter.metrics_reader.get_metrics_data()).to_json())  # type: ignore

    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    # collected metrics vary by platform, etc.
    # assert that we at least collected _some_ of the metrics we expect
    assert metrics_collected.issuperset(
        {
            'system.swap.usage',
            'system.disk.operations',
            'system.memory.usage',
            'system.cpu.utilization',
        }
    ), metrics_collected
```

Let's walk through the utilities we used.

### [`IncrementalIdGenerator`][logfire.testing.IncrementalIdGenerator]

One of the most complicated things about comparing log output to expected results are sources of non-determinism.
For OpenTelemetry spans the two biggest ones are the span & trace IDs and timestamps.

The [`IncrementalIdGenerator`][logfire.testing.IncrementalIdGenerator] generates sequentially increasing span
and trace IDs so that test outputs are always the same.

### [TimeGenerator][logfire.testing.TimeGenerator]

This class generates nanosecond timestamps that increment by 1s every time a timestamp is generated.

### [`logfire.configure`][logfire.configure]

This is the same configuration function you'd use for production and where everything comes together.

Note that we specifically configure:

- `send_to_logfire=False` because we don't want to hit the actual production service
- `id_generator=IncrementalIdGenerator()` to make the span IDs deterministic
- `ns_timestamp_generator=TimeGenerator()` to make the timestamps deterministic
- `processors=[SimpleSpanProcessor(exporter)]` to use our `TestExporter` to capture spans. We use `SimpleSpanProcessor` to export spans with no delay.

### `insert_assert`

This is a utility function provided by [devtools](https://github.com/samuelcolvin/python-devtools) that will automatically insert the output of the code it is called with into the test file when run via pytest. That is, if you comment that line out you'll see that the `assert logfire_test_exporter.exported_spans_as_dict() == [...]` line is replaced with the current output of `logfire_test_exporter.exported_spans_as_dict()`, which should be exactly the same given that our test is deterministic!
