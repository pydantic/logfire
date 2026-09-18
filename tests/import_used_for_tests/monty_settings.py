import json
from io import StringIO
from typing import Any

from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic_monty import CollectString, Monty

import logfire
from logfire.testing import IncrementalIdGenerator, TestExporter, TestLogExporter, TimeGenerator, get_collected_metrics

exporter = TestExporter()
logs_exporter = TestLogExporter(TimeGenerator())
console = StringIO()
config_kwargs: dict[str, Any] = dict(
    send_to_logfire=False,
    console=logfire.ConsoleOptions(output=console, colors='never'),
    inspect_arguments=False,
    advanced=logfire.AdvancedOptions(
        id_generator=IncrementalIdGenerator(),
        log_record_processors=[SimpleLogRecordProcessor(logs_exporter)],
    ),
    additional_span_processors=[SimpleSpanProcessor(exporter)],
)
logfire.configure(**config_kwargs, metrics=False, min_level='error')
logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.5).with_settings(
    tags=['monty'], console_log=False
).instrument_monty()

with Monty(min_processes=1, max_processes=1) as pool:
    with pool.checkout() as session:
        assert session.feed_run("print('before')\n1 + 2", print_callback=CollectString()) == 3
    assert logs_exporter.exported_logs_as_dicts() == []

    reader = InMemoryMetricReader()
    logs_exporter = TestLogExporter(TimeGenerator())
    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(logs_exporter)]
    logfire.configure(**config_kwargs, metrics=logfire.MetricsOptions(additional_readers=[reader]))
    logfire.with_settings(tags=['ignored']).instrument_monty()
    exporter.clear()

    with pool.checkout() as session:
        assert session.feed_run("print('after')\n6 * 7", print_callback=CollectString()) == 42

print(
    json.dumps(
        {
            'spans': [
                {
                    'name': span['name'],
                    'tags': span['attributes']['logfire.tags'],
                    'sample_rate': span['attributes']['logfire.sample_rate'],
                    'scope': span['instrumentation_scope'],
                }
                for span in exporter.exported_spans_as_dict(include_instrumentation_scope=True)
            ],
            'logs': [
                {
                    'body': record['body'],
                    'tags': record['attributes']['logfire.tags'],
                    'disable_console_log': record['attributes']['logfire.disable_console_log'],
                }
                for record in logs_exporter.exported_logs_as_dicts()
            ],
            'metrics': sorted(metric['name'] for metric in get_collected_metrics(reader)),
            'printed_log_to_console': 'print stdout' in console.getvalue(),
        }
    )
)
