# Inspired by:
# https://github.com/open-telemetry/opentelemetry-python-contrib/blob/e318c947a23152c8ff1700f0aad44261be0588cd/instrumentation/opentelemetry-instrumentation-wsgi/src/opentelemetry/instrumentation/wsgi/__init__.py
from __future__ import annotations

from typing import Any, Callable

from opentelemetry.instrumentation.wsgi import collect_request_attributes  # type: ignore

from logfire import Logfire, get_default_logger


class LogfireMiddleware:
    def __init__(self, wsgi: Any, logfire: Logfire | None = None) -> None:
        self._wsgi = wsgi
        self._logfire = logfire or get_default_logger()

    @staticmethod
    def _get_attributes(environ: dict[str, Any]) -> dict[str, Any]:
        return collect_request_attributes(environ)  # type: ignore

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., None]) -> Any:
        """The WSGI application

        Args:
            environ: A WSGI environment.
            start_response: The WSGI start_response callable.
        """
        attributes = self._get_attributes(environ)
        attributes['method'] = environ.get('REQUEST_METHOD', '').strip()
        attributes['path'] = environ.get('PATH_INFO', '').strip()
        with self._logfire.span('{method} {path}', **attributes):
            return self._wsgi(environ, start_response)
