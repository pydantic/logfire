"""Regression tests for how generator observable callbacks are primed.

``_sanitize_observable_callbacks`` primes a generator callback with ``next()`` (mirroring
the OpenTelemetry SDK's ``_Observable.__init__``) and hands the SDK a plain callable, which
then drives the generator with ``send(options)``. A proxy instrument re-creates its real
instrument every time a meter provider is set on the proxy provider, so the caller's
generator must be primed exactly once: priming it again advances an already-primed
generator, which either drops a collection or makes a callback that consumes the sent
``CallbackOptions`` raise.
"""

from __future__ import annotations

import warnings
from collections.abc import Generator, Iterable, Sequence

from opentelemetry.metrics import CallbackOptions, CallbackT, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from logfire._internal.metrics import (
    _ProxyObservableCounter,  # pyright: ignore[reportPrivateUsage]
)


def _observable_counter(provider: MeterProvider, callbacks: Sequence[CallbackT]) -> _ProxyObservableCounter:
    return _ProxyObservableCounter(
        provider.get_meter('priming'),
        name='priming_counter',
        unit='',
        description='',
        callbacks=callbacks,
    )


def test_generator_callback_is_primed_once_across_meter_reconfiguration() -> None:
    advances: list[int] = []

    def callback() -> Generator[Iterable[Observation], CallbackOptions, None]:
        count = 0
        while True:
            count += 1
            advances.append(count)
            yield [Observation(count, {})]

    provider = MeterProvider()
    instrument = _observable_counter(provider, [callback()])

    # What a meter-provider reconfiguration does to every existing proxy instrument.
    instrument.on_meter_set(provider.get_meter('priming'))

    assert advances == [1]


def test_generator_callback_that_consumes_options_survives_meter_reconfiguration() -> None:
    def callback() -> Generator[Iterable[Observation], CallbackOptions, None]:
        options = yield []
        while True:
            options = yield [Observation(1, {'timeout_millis': options.timeout_millis, 'bad': object()})]  # pyright: ignore[reportArgumentType]

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    instrument = _observable_counter(provider, [callback()])

    # Priming again would send ``None`` into the loop above and raise from the generator.
    instrument.on_meter_set(provider.get_meter('priming'))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        provider.force_flush()

    # The sanitizing wrapper still runs, and still drops the unsupported value: the
    # generator's ``send()`` path is reached exactly as before.
    assert any('Dropping metric attribute' in str(w.message) for w in caught), [str(w.message) for w in caught]
