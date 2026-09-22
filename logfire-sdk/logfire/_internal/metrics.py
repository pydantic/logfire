from __future__ import annotations

import dataclasses
import warnings
from abc import ABC, abstractmethod
from collections.abc import Sequence
from threading import Lock
from typing import Any, Generic, TypeVar
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
    _Gauge as Gauge,
)
from opentelemetry.sdk.metrics import MeterProvider as SDKMeterProvider
from opentelemetry.trace import get_current_span
from opentelemetry.util.types import Attributes

from .tracer import _LogfireWrappedSpan  # pyright: ignore[reportPrivateUsage]
from .utils import handle_internal_errors

# Types that a metric data point attribute value may have.
# A value must be encodable by the OTLP exporter AND hashable, because the metrics SDK keys
# aggregations on frozenset(attributes.items()). So the accepted set is a primitive, or a
# tuple (hashable) of primitives. Unlike span attributes, metric attributes are not passed
# through logfire's prepare_otlp_attribute, and neither the metrics SDK nor the exporter
# cleans them, so an unsupported value only fails later: either inside the exporter thread
# (dropping the whole batch, with no pointer to the offending call) or during aggregation
# with a raw TypeError. See https://github.com/pydantic/logfire/issues/782.
_VALID_METRIC_ATTRIBUTE_TYPES = (bool, str, bytes, int, float)


def _sanitize_metric_attributes(attributes: Attributes | None) -> Attributes | None:
    """Drop metric attribute values that break the exporter or aggregation, warning for each.

    A single bad value otherwise either raises inside `PeriodicExportingMetricReader`'s
    background thread (dropping the whole batch, with no pointer to the offending call) or
    raises a raw TypeError during aggregation for unhashable values. Warning and dropping the
    individual attribute keeps the metric and its other attributes instead.
    """
    if not attributes:
        return attributes

    cleaned: dict[str, Any] | None = None
    for key, value in attributes.items():
        if not _metric_attribute_value_is_valid(value):
            warnings.warn(
                f'Dropping metric attribute {key!r} with invalid type {type(value).__name__}. '
                f'Metric attribute values must be one of '
                f'{[t.__name__ for t in _VALID_METRIC_ATTRIBUTE_TYPES]}, or a tuple of those.',
                UserWarning,
                stacklevel=3,
            )
            if cleaned is None:
                cleaned = dict(attributes)
            del cleaned[key]

    return cleaned if cleaned is not None else attributes


def _metric_attribute_value_is_valid(value: Any) -> bool:
    if isinstance(value, _VALID_METRIC_ATTRIBUTE_TYPES):
        return True
    # A tuple of primitives is hashable and OTLP-encodable; a list is a valid OTLP attribute
    # value in general but is unhashable and crashes the metrics SDK's aggregation keying
    # (frozenset(attributes.items())), so only tuples are accepted here.
    if isinstance(value, tuple):
        return all(element is None or isinstance(element, _VALID_METRIC_ATTRIBUTE_TYPES) for element in value)
    return False


# The following proxy classes are adapted from OTEL's SDK
@dataclasses.dataclass
class ProxyMeterProvider(MeterProvider):
    provider: MeterProvider
    meters: WeakSet[_ProxyMeter] = dataclasses.field(default_factory=WeakSet['_ProxyMeter'])
    lock: Lock = dataclasses.field(default_factory=Lock)
    suppressed_scopes: set[str] = dataclasses.field(default_factory=set[str])

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

    def force_flush(self, timeout_millis: float = 30_000) -> None:
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

    def _add_proxy_instrument(self, instrument_type: type[_ProxyInstrument[InstrumentT]], **kwargs: Any) -> InstrumentT:
        with self._lock:
            proxy = instrument_type(self._meter, **kwargs)
            self._instruments.add(proxy)
            return proxy  # pyright: ignore[reportReturnType]

    def create_counter(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> Counter:
        return self._add_proxy_instrument(_ProxyCounter, name=name, unit=unit, description=description)

    def create_up_down_counter(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> UpDownCounter:
        return self._add_proxy_instrument(_ProxyUpDownCounter, name=name, unit=unit, description=description)

    def create_observable_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableCounter:
        return self._add_proxy_instrument(
            _ProxyObservableCounter, name=name, unit=unit, description=description, callbacks=callbacks
        )

    def create_histogram(
        self,
        name: str,
        unit: str = '',
        description: str = '',
        **kwargs: Any,
    ) -> Histogram:
        return self._add_proxy_instrument(_ProxyHistogram, name=name, unit=unit, description=description, **kwargs)

    def create_gauge(
        self,
        name: str,
        unit: str = '',
        description: str = '',
    ) -> Gauge:
        return self._add_proxy_instrument(_ProxyGauge, name=name, unit=unit, description=description)

    def create_observable_gauge(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableGauge:
        return self._add_proxy_instrument(
            _ProxyObservableGauge, name=name, unit=unit, description=description, callbacks=callbacks
        )

    def create_observable_up_down_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = '',
        description: str = '',
    ) -> ObservableUpDownCounter:
        return self._add_proxy_instrument(
            _ProxyObservableUpDownCounter, name=name, unit=unit, description=description, callbacks=callbacks
        )


InstrumentT = TypeVar('InstrumentT', bound=Instrument)


class _ProxyInstrument(ABC, Generic[InstrumentT]):
    def __init__(self, meter: Meter, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._instrument = self._create_real_instrument(meter)

    def on_meter_set(self, meter: Meter) -> None:
        """Called when a real meter is set on the creating _ProxyMeter."""
        # We don't need any locking on proxy instruments because it's OK if some
        # measurements get dropped while a real backing instrument is being
        # created.
        self._instrument = self._create_real_instrument(meter)

    @abstractmethod
    def _create_real_instrument(self, meter: Meter) -> InstrumentT:
        """Create an instance of the real instrument. Implement this."""

    @handle_internal_errors
    def _increment_span_metric(self, amount: float, attributes: Attributes | None = None):
        span = get_current_span()
        if isinstance(span, _LogfireWrappedSpan):
            span.increment_metric(self._kwargs['name'], attributes or {}, amount)


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
        self._increment_span_metric(amount, attributes)
        self._instrument.add(amount, _sanitize_metric_attributes(attributes), *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> Counter:
        return meter.create_counter(**self._kwargs)


class _ProxyHistogram(_ProxyInstrument[Histogram], Histogram):
    def record(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._increment_span_metric(amount, attributes)
        self._instrument.record(amount, _sanitize_metric_attributes(attributes), *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> Histogram:
        return meter.create_histogram(**self._kwargs)


class _ProxyObservableCounter(_ProxyInstrument[ObservableCounter], ObservableCounter):
    def _create_real_instrument(self, meter: Meter) -> ObservableCounter:
        return meter.create_observable_counter(**self._kwargs)


class _ProxyObservableGauge(_ProxyInstrument[ObservableGauge], ObservableGauge):
    def _create_real_instrument(self, meter: Meter) -> ObservableGauge:
        return meter.create_observable_gauge(**self._kwargs)


class _ProxyObservableUpDownCounter(_ProxyInstrument[ObservableUpDownCounter], ObservableUpDownCounter):
    def _create_real_instrument(self, meter: Meter) -> ObservableUpDownCounter:
        return meter.create_observable_up_down_counter(**self._kwargs)


class _ProxyUpDownCounter(_ProxyInstrument[UpDownCounter], UpDownCounter):
    def add(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._instrument.add(amount, _sanitize_metric_attributes(attributes), *args, **kwargs)

    def _create_real_instrument(self, meter: Meter) -> UpDownCounter:
        return meter.create_up_down_counter(**self._kwargs)


class _ProxyGauge(_ProxyInstrument[Gauge], Gauge):
    def set(
        self,
        amount: int | float,
        attributes: Attributes | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._instrument.set(amount, _sanitize_metric_attributes(attributes), *args, **kwargs)

    def _create_real_instrument(self, meter: Meter):
        return meter.create_gauge(**self._kwargs)

