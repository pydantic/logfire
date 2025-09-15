from __future__ import annotations

from collections.abc import Callable
from multidict import CIMultiDict
from opentelemetry.trace import Span
from aiohttp.tracing import TraceRequestStartParams, TraceRequestEndParams, TraceRequestExceptionParams

AioHttpHeaders = CIMultiDict[str]
RequestHook = Callable[[Span, TraceRequestStartParams], None]
ResponseHook = Callable[[Span, TraceRequestEndParams | TraceRequestExceptionParams], None]