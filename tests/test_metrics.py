import json
import os
from typing import cast

from dirty_equals import IsDict, IsFloat, IsList, IsPositiveFloat, IsPositiveInt, IsStr
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData
from opentelemetry.sdk.resources import SERVICE_NAME

from logfire.version import VERSION


def test_metric_exporter(metrics_reader: InMemoryMetricReader) -> None:
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    # insert_assert(exported_metrics)
    assert exported_metrics == {
        'resource_metrics': [
            {
                'resource': {
                    'attributes': {
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': IsStr(),
                        SERVICE_NAME: 'unknown_service',
                    },
                    'schema_url': '',
                },
                'scope_metrics': [
                    {
                        'scope': {
                            'name': 'opentelemetry.instrumentation.logfire',
                            'version': VERSION,
                            'schema_url': '',
                        },
                        'metrics': [
                            {
                                'name': 'system.cpu.usage',
                                'description': 'CPU usage',
                                'unit': '%',
                                'data': {'data_points': IsList(length=os.cpu_count())},
                            },
                            {
                                'name': 'system.ram.usage',
                                'description': 'RAM usage',
                                'unit': '%',
                                'data': {
                                    'data_points': IsList(
                                        IsDict(
                                            {
                                                'attributes': {'type': 'ram'},
                                                'start_time_unix_nano': 0,
                                                'time_unix_nano': IsPositiveInt(),
                                                'value': IsPositiveFloat(),
                                            }
                                        ),
                                        IsDict(
                                            {
                                                'attributes': {'type': 'swap'},
                                                'start_time_unix_nano': 0,
                                                'time_unix_nano': IsPositiveInt(),
                                                'value': IsFloat(),
                                            }
                                        ),
                                    ),
                                },
                            },
                        ],
                        'schema_url': '',
                    }
                ],
                'schema_url': '',
            }
        ]
    }
