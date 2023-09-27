from __future__ import annotations

from typing import Iterable

import psutil
from opentelemetry.metrics import CallbackOptions, Observation, get_meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader

from logfire.version import VERSION


def cpu_usage_callback(_: CallbackOptions):
    for number, percent in enumerate(psutil.cpu_percent(percpu=True)):
        attributes = {'cpu_number': str(number)}
        yield Observation(percent, attributes)


def ram_usage_callback(_: CallbackOptions) -> Iterable[Observation]:
    ram_percent = psutil.virtual_memory().percent
    swap_percent = psutil.swap_memory().percent
    yield Observation(ram_percent, {'type': 'ram'})
    yield Observation(swap_percent, {'type': 'swap'})


def set_meter_provider(exporter: MetricExporter) -> MeterProvider:
    """Setup metrics for the logfire package.

    Args:
        exporter: The exporter to use for exporting metrics.
    """
    metric_reader = PeriodicExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=[metric_reader])

    meter = get_meter('opentelemetry.instrumentation.logfire', version=VERSION, meter_provider=meter_provider)
    meter.create_observable_gauge('system.cpu.usage', callbacks=[cpu_usage_callback], unit='%', description='CPU usage')
    meter.create_observable_gauge('system.ram.usage', callbacks=[ram_usage_callback], unit='%', description='RAM usage')

    return meter_provider
