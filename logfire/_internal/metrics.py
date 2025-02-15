from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from threading import Lock
from typing import Any, Generic, Sequence, TypeVar
from weakref import WeakSet

from opentelemetry.metrics import (
    CallbackT,
    Counter,
    Histogram,
    Instrument,
    Meter,
    MeterProvider,
    NoOpMeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics import MeterProvider as SDKMeterProvider
from opentelemetry.util.types import Attributes

try:
    # This only exists in opentelemetry-sdk>=1.23.0
    from opentelemetry.metrics import _Gauge

    Gauge = _Gauge
except ImportError:  # pragma: no cover
    Gauge = None


# The following proxy classes are adapted from OTEL's SDK
@dataclasses.dataclass
class ProxyMeterProvider(MeterProvider):
    provider: MeterProvider
    meters: WeakSet[_ProxyMeter] = dataclasses.field(default_factory=WeakSet)
    lock: Lock = dataclasses.field(default_factory=Lock)
    suppressed_scopes: set[str] = dataclasses.field(default_factory=set)

    def get_meter(
        self,
        name: str,
        version: str | None = None,
        schema_url: str | None = None,
        attributes: Attributes | None = None,
    ) -> Meter:
        with self.lock:
            if name in self.suppressed_scopes:
                provider = NoOpMeterProvider()
            else:
                provider = self.provider
            inner_meter = provider.get_meter(name, version, schema_url, *[attributes] if attributes is not None else [])
            meter = _ProxyMeter(inner_meter, name, version, schema_url)
            self.meters.add(meter)
            return meter

    def suppress_scopes(self, *scopes: str) -> None:
        with self.lock:
            self.suppressed_scopes.update(scopes)
            for meter in self.meters:
                if meter.name in scopes:
                    meter.set_meter(NoOpMeterProvider())

    def set_meter_provider(self, meter_provider: MeterProvider) -> None:
        with self.lock:
            self.provider = meter_provider
            for meter in self.meters:
                meter.set_meter(NoOpMeterProvider() if meter.name in self.suppressed_scopes else meter_provider)

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        with self.lock:
            if isinstance(self.provider, SDKMeterProvider):
                self.provider.shutdown(timeout_millis)

    def force_flush(self, timeout_millis: float = 30_000) -> None:  # pragma: no cover
        with self.lock:
            if isinstance(self.provider, SDKMeterProvider):  # pragma: no branch
                self.provider.force_flush(timeout_millis)


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
        self._instruments: WeakSet[_ProxyInstrument[Any]] = WeakSet()

    def set_meter(self, meter_provider: MeterProvider) -> None:
        """Called when a real meter provider is set on the creating _ProxyMeterProvider.

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
        **kwargs: Any,
    ) -> Histogram:
        with self._lock:
            proxy = _ProxyHistogram(
                self._meter.create_histogram(name, unit, description, **kwargs), name, unit, description
            )
            self._instruments.add(proxy)
            return proxy

    def create_gauge(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> _Gauge:
        if Gauge is None:
            # This only exists in opentelemetry-sdk>=1.23.0
            raise RuntimeError(
                'Gauge is not available in this version of OpenTelemetry SDK.\n'
                'You should upgrade to 1.23.0 or newer:\n'
                '   pip install opentelemetry-sdk>=1.23.0'
            )
        with self._lock:
            proxy = _ProxyGauge(self._meter.create_gauge(name, unit, description), name, unit, description)
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
        """Called when a real meter is set on the creating _ProxyMeter."""
        # We don't need any locking on proxy instruments because it's OK if some
        # measurements get dropped while a real backing instrument is being
        # created.
        self._instrument = self._create_real_instrument(meter)

    @abstractmethod
    def _create_real_instrument(self, meter: Meter) -> InstrumentT:
        """Create an instance of the real instrument. Implement this."""


class _ProxyAsynchronousInstrument(_ProxyInstrument[InstrumentT], ABC):
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
        # Starting with opentelemetry-sdk 1.28.0, these methods accept an additional optional `context` argument.
        # This is passed to the underlying instrument using `*args, **kwargs` for compatibility with older versions.
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._instrument.add(amount, attributes, *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> Counter:
        return meter.create_counter(self._name, self._unit, self._description)


class _ProxyHistogram(_ProxyInstrument[Histogram], Histogram):
    def record(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._instrument.record(amount, attributes, *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> Histogram:
        return meter.create_histogram(self._name, self._unit, self._description)


class _ProxyObservableCounter(_ProxyAsynchronousInstrument[ObservableCounter], ObservableCounter):
    def _create_real_instrument(self, meter: Meter) -> ObservableCounter:  # pragma: no cover
        return meter.create_observable_counter(self._name, self._callbacks, self._unit, self._description)


class _ProxyObservableGauge(
    _ProxyAsynchronousInstrument[ObservableGauge],
    ObservableGauge,
):
    def _create_real_instrument(self, meter: Meter) -> ObservableGauge:  # pragma: no cover
        return meter.create_observable_gauge(self._name, self._callbacks, self._unit, self._description)


class _ProxyObservableUpDownCounter(
    _ProxyAsynchronousInstrument[ObservableUpDownCounter],
    ObservableUpDownCounter,
):
    def _create_real_instrument(self, meter: Meter) -> ObservableUpDownCounter:  # pragma: no cover
        return meter.create_observable_up_down_counter(self._name, self._callbacks, self._unit, self._description)


class _ProxyUpDownCounter(_ProxyInstrument[UpDownCounter], UpDownCounter):
    def add(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._instrument.add(amount, attributes, *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> UpDownCounter:
        return meter.create_up_down_counter(self._name, self._unit, self._description)


if Gauge is not None:  # pragma: no branch

    class _ProxyGauge(_ProxyInstrument[Gauge], Gauge):
        def set(
            self,
            amount: int | float,
            attributes: Attributes | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:  # pragma: no cover
            self._instrument.set(amount, attributes, *args, **kwargs)

        def _create_real_instrument(self, meter: Meter):  # pragma: no cover
            return meter.create_gauge(self._name, self._unit, self._description)
else:  # pragma: no cover
    _ProxyGauge = None  # type: ignore
