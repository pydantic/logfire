import json
import os

from dirty_equals import IsDict, IsFloat, IsList, IsPositiveFloat, IsPositiveInt, IsStr
from opentelemetry.sdk.resources import SERVICE_NAME

from logfire import Logfire
from logfire._metrics import set_meter_provider
from logfire.version import VERSION

from .conftest import TestMetricExporter


def test_metric_exporter(logfire: Logfire, metric_exporter: TestMetricExporter) -> None:
    meter_provider = set_meter_provider(metric_exporter)
    meter_provider.force_flush()

    exported_metrics = [json.loads(metric.to_json()) for metric in metric_exporter.exported_metrics]
    # insert_assert(exported_metrics)
    assert exported_metrics == [
        {
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
    ]
