from __future__ import annotations

from typing import Any, Literal

from pydantic_ai import Agent
from pydantic_ai.agent import InstrumentationSettings
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentedModel

from logfire import Logfire


def instrument_pydantic_ai(
    logfire_instance: Logfire,
    obj: Agent | Model | None,
    event_mode: Literal['attributes', 'logs'] | None,
    **kwargs: Any,
) -> None | InstrumentedModel:
    if event_mode is None:
        event_mode = InstrumentationSettings.event_mode
    kwargs = dict(
        tracer_provider=logfire_instance.config.get_tracer_provider(),
        event_logger_provider=logfire_instance.config.get_event_logger_provider(),
        event_mode=event_mode,
        **kwargs,
    )
    try:
        settings = InstrumentationSettings(
            meter_provider=logfire_instance.config.get_meter_provider(),
            **kwargs,
        )
    except TypeError:  # pragma: no cover
        # Handle older pydantic-ai versions that do not support meter_provider.
        settings = InstrumentationSettings(
            **kwargs,
        )
    if isinstance(obj, Agent):
        obj.instrument = settings
    elif isinstance(obj, Model):
        return InstrumentedModel(obj, settings)
    elif obj is None:
        Agent.instrument_all(settings)
    else:
        raise TypeError(f'Cannot instrument object of type {type(obj)}')
