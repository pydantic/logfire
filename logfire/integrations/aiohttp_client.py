from __future__ import annotations

from collections.abc import Callable

from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from multidict import CIMultiDict
from opentelemetry.trace import Span

AioHttpHeaders = CIMultiDict[str]
RequestHook = Callable[[Span, TraceRequestStartParams], None]
ResponseHook = Callable[[Span, TraceRequestEndParams | TraceRequestExceptionParams], None]
