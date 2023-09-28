from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation.asgi import collect_request_attributes  # type: ignore

from logfire import Logfire, get_default_logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class LogfireMiddleware:
    def __init__(self, app: ASGIApp, logfire: Logfire | None = None) -> None:
        self._app = app
        self._logfire = logfire or get_default_logger()

    @staticmethod
    def _get_attributes(scope: Scope) -> dict[str, Any]:
        return collect_request_attributes(scope)  # type: ignore[no-untyped-call,no-any-return]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websockets'):
            return await self._app(scope, receive, send)

        attributes = self._get_attributes(scope)
        attributes['method'] = scope.get('method')
        attributes['path'] = scope.get('path')
        with self._logfire.span('{method} {path}', **attributes):
            await self._app(scope, receive, send)
