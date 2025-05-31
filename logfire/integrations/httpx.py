from __future__ import annotations

# TODO(Marcelo): When https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3098/ gets merged,
# and the next version of `opentelemetry-instrumentation-httpx` is released, we can just do a reimport:
from opentelemetry.instrumentation.httpx import (
    AsyncRequestHook as AsyncRequestHook,
    AsyncResponseHook as AsyncResponseHook,
    RequestHook as RequestHook,
    RequestInfo as RequestInfo,
    ResponseHook as ResponseHook,
    ResponseInfo as ResponseInfo,
)
