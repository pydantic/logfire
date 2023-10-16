from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from threading import Lock
from typing import Generic, Iterable, Sequence, TypeVar, Union
from weakref import WeakSet

import psutil
from opentelemetry.metrics import (
    CallbackOptions,
    CallbackT,
    Counter,
    Histogram,
    Instrument,
    Meter,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    Observation,
    UpDownCounter,
    get_meter,
)
from opentelemetry.util.types import Attributes

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


def configure_metrics(meter_provider: MeterProvider) -> None:
    meter = get_meter('opentelemetry.instrumentation.logfire', version=VERSION, meter_provider=meter_provider)
    meter.create_observable_gauge('system.cpu.usage', callbacks=[cpu_usage_callback], unit='%', description='CPU usage')
    meter.create_observable_gauge('system.ram.usage', callbacks=[ram_usage_callback], unit='%', description='RAM usage')


# The following proxy classes are adapted from OTEL's SDK


@dataclasses.dataclass
class ProxyMeterProvider(MeterProvider):
    provider: MeterProvider
    meters: WeakSet[_ProxyMeter] = dataclasses.field(default_factory=WeakSet)
    lock: Lock = dataclasses.field(default_factory=Lock)

    def get_meter(
        self,
        name: str,
        version: str | None = None,
        schema_url: str | None = None,
    ) -> Meter:
        with self.lock:
            meter = _ProxyMeter(
                self.provider.get_meter(name, version=version, schema_url=schema_url),
                name,
                version,
                schema_url,
            )
            self.meters.add(meter)
            return meter

    def set_meter_provider(self, meter_provider: MeterProvider) -> None:
        with self.lock:
            self.provider = meter_provider
            for meter in self.meters:
                meter.set_meter(meter_provider)


class _ProxyMeter(Meter):
    def __init__(
        self,
        meter: Meter,
        name: str,
        version: str | None,
        schema_url: str | None,
    ) -> None:
        super().__init__(name, version=version, schema_url=schema_url)
        self._lock = Lock()
        self._meter = meter
        self._instruments: WeakSet[_ProxyInstrumentT] = WeakSet()

    def set_meter(self, meter_provider: MeterProvider) -> None:
        """Called when a real meter provider is set on the creating _ProxyMeterProvider

        Creates a real backing meter for this instance and notifies all created
        instruments so they can create real backing instruments.
        """
        real_meter = meter_provider.get_meter(self._name, self._version, self._schema_url)

        with self._lock:
            self._meter = real_meter
            # notify all proxy instruments of the new meter so they can create
            # real instruments to back themselves
            for instrument in self._instruments:
                instrument.on_meter_set(real_meter)

    def create_counter(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> Counter:
        with self._lock:
            proxy = _ProxyCounter(self._meter.create_counter(name, unit, description), name, unit, description)
            self._instruments.add(proxy)
            return proxy

    def create_up_down_counter(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> UpDownCounter:
        with self._lock:
            proxy = _ProxyUpDownCounter(
                self._meter.create_up_down_counter(name, unit, description), name, unit, description
            )
            self._instruments.add(proxy)
            return proxy

    def create_observable_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableCounter:
        with self._lock:
            proxy = _ProxyObservableCounter(
                self._meter.create_observable_counter(name, callbacks, unit, description),
                name,
                callbacks,
                unit,
                description,
            )
            self._instruments.add(proxy)
            return proxy

    def create_histogram(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> Histogram:
        with self._lock:
            proxy = _ProxyHistogram(self._meter.create_histogram(name, unit, description), name, unit, description)
            self._instruments.add(proxy)
            return proxy

    def create_observable_gauge(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableGauge:
        with self._lock:
            proxy = _ProxyObservableGauge(
                self._meter.create_observable_gauge(name, callbacks, unit, description),
                name,
                callbacks,
                unit,
                description,
            )
            self._instruments.add(proxy)
            return proxy

    def create_observable_up_down_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableUpDownCounter:
        with self._lock:
            proxy = _ProxyObservableUpDownCounter(
                self._meter.create_observable_up_down_counter(name, callbacks, unit, description),
                name,
                callbacks,
                unit,
                description,
            )
            self._instruments.add(proxy)
            return proxy


InstrumentT = TypeVar('InstrumentT', bound=Instrument)


class _ProxyInstrument(ABC, Generic[InstrumentT]):
    def __init__(
        self,
        instrument: InstrumentT,
        name: str,
        unit: str,
        description: str,
    ) -> None:
        self._name = name
        self._unit = unit
        self._description = description
        self._instrument = instrument

    def on_meter_set(self, meter: Meter) -> None:
        """Called when a real meter is set on the creating _ProxyMeter"""
        # We don't need any locking on proxy instruments because it's OK if some
        # measurements get dropped while a real backing instrument is being
        # created.
        self._instrument = self._create_real_instrument(meter)

    @abstractmethod
    def _create_real_instrument(self, meter: Meter) -> InstrumentT:
        """Create an instance of the real instrument. Implement this."""


class _ProxyAsynchronousInstrument(_ProxyInstrument[InstrumentT]):
    def __init__(
        self,
        instrument: InstrumentT,
        name: str,
        callbacks: Sequence[CallbackT] | None,
        unit: str,
        description: str,
    ) -> None:
        super().__init__(instrument, name, unit, description)
        self._callbacks = callbacks


class _ProxyCounter(_ProxyInstrument[Counter], Counter):
    def add(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
    ) -> None:
        self._instrument.add(amount, attributes)

    def _create_real_instrument(self, meter: Meter) -> Counter:
        return meter.create_counter(self._name, self._unit, self._description)


class _ProxyHistogram(_ProxyInstrument[Histogram], Histogram):
    def record(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
    ) -> None:
        self._instrument.record(amount, attributes)

    def _create_real_instrument(self, meter: Meter) -> Histogram:
        return meter.create_histogram(self._name, self._unit, self._description)


class _ProxyObservableCounter(_ProxyAsynchronousInstrument[ObservableCounter], ObservableCounter):
    def _create_real_instrument(self, meter: Meter) -> ObservableCounter:
        return meter.create_observable_counter(self._name, self._callbacks, self._unit, self._description)


class _ProxyObservableGauge(
    _ProxyAsynchronousInstrument[ObservableGauge],
    ObservableGauge,
):
    def _create_real_instrument(self, meter: Meter) -> ObservableGauge:
        return meter.create_observable_gauge(self._name, self._callbacks, self._unit, self._description)


class _ProxyObservableUpDownCounter(
    _ProxyAsynchronousInstrument[ObservableUpDownCounter],
    ObservableUpDownCounter,
):
    def _create_real_instrument(self, meter: Meter) -> ObservableUpDownCounter:
        return meter.create_observable_up_down_counter(self._name, self._callbacks, self._unit, self._description)


class _ProxyUpDownCounter(_ProxyInstrument[UpDownCounter], UpDownCounter):
    def add(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
    ) -> None:
        self._instrument.add(amount, attributes)

    def _create_real_instrument(self, meter: Meter) -> UpDownCounter:
        return meter.create_up_down_counter(self._name, self._unit, self._description)


_ProxyInstrumentT = Union[
    _ProxyCounter,
    _ProxyHistogram,
    _ProxyObservableCounter,
    _ProxyObservableGauge,
    _ProxyObservableUpDownCounter,
    _ProxyUpDownCounter,
]
