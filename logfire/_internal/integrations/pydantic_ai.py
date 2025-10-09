from __future__ import annotations

import inspect
from typing import Any, Literal

from pydantic_ai import Agent
from pydantic_ai.agent import InstrumentationSettings
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentedModel

from logfire import Logfire


def instrument_pydantic_ai(
    logfire_instance: Logfire,
    obj: Agent | Model | None,
    include_binary_content: bool | None,
    include_content: bool | None,
    version: Literal[1, 2, 3] | None,
    event_mode: Literal['attributes', 'logs'] | None,
    **kwargs: Any,
) -> None | InstrumentedModel:
    expected_kwarg_names = inspect.signature(InstrumentationSettings.__init__).parameters
    final_kwargs: dict[str, Any] = {
        k: v
        for k, v in dict(
            tracer_provider=logfire_instance.config.get_tracer_provider(),
            meter_provider=logfire_instance.config.get_meter_provider(),
            event_logger_provider=logfire_instance.config.get_event_logger_provider(),
        ).items()
        if k in expected_kwarg_names
    }
    final_kwargs.update(
        {
            k: v
            for k, v in dict(
                include_binary_content=include_binary_content,
                include_content=include_content,
                version=version,
                event_mode=event_mode,
            ).items()
            if v is not None
        }
    )
    final_kwargs.update(kwargs)
    settings = InstrumentationSettings(**final_kwargs)
    if isinstance(obj, Agent):
        obj.instrument = settings
    elif isinstance(obj, Model):
        return InstrumentedModel(obj, settings)
    elif obj is None:
        Agent.instrument_all(settings)
    else:
        raise TypeError(f'Cannot instrument object of type {type(obj)}')
