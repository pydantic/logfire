from typing import Any

from opentelemetry.instrumentation.asgi import collect_request_attributes  # type: ignore
from starlette.types import ASGIApp, Receive, Scope, Send

from logfire import Observe, _instance  # type: ignore


class LogfireFastAPIMiddleware:
    def __init__(self, app: ASGIApp, observe: Observe = _instance) -> None:
        self._app = app
        self._observe = observe

    def _get_attributes(self, scope: Scope) -> dict[str, Any]:
        return collect_request_attributes(scope)  # type: ignore[no-untyped-call,no-any-return]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websockets'):
            return await self._app(scope, receive, send)

        attributes = self._get_attributes(scope)
        attributes['method'] = scope.get('method')
        attributes['path'] = scope.get('path')
        with self._observe.span('request', '{method} {path}', **attributes):
            await self._app(scope, receive, send)
