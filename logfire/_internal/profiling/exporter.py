"""Export OTLP profiles over HTTP.

The OpenTelemetry profiles signal has no SDK exporter yet, so this posts the
protobuf directly. In production the `session` should be Logfire's
`OTLPExporterHttpSession` (disk-retry, gzip, the token `Authorization` header),
and `endpoint` the region base URL joined with the profiles path below.

Everything here fails soft: a profiling problem must never disrupt the app or
the other signals, so `export()` returns a bool and never raises.
"""

from __future__ import annotations

import gzip
import warnings
from typing import Protocol

from ._proto.profiles_service_pb2 import ExportProfilesServiceRequest

# Profiles is still a development signal - note the path is NOT `/v1/profiles`.
PROFILES_PATH = '/v1development/profiles'


class _Response(Protocol):
    # Read-only properties so a `requests.Response` (whose `text` is a property) satisfies this.
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...


class _PostSession(Protocol):
    def post(self, url: str, *, data: bytes, headers: dict[str, str], timeout: float) -> _Response: ...


class ProfilesExporter:
    """Posts OTLP profiles to an HTTP endpoint, failing soft on any error."""

    def __init__(self, session: _PostSession, endpoint: str, *, timeout: float = 10.0) -> None:
        self._session = session
        self._endpoint = endpoint
        self._timeout = timeout

    def export(self, request: ExportProfilesServiceRequest) -> bool:
        """Serialize, gzip and POST the request. Returns True on a 2xx response."""
        try:
            payload = gzip.compress(request.SerializeToString())
            response = self._session.post(
                self._endpoint,
                data=payload,
                headers={
                    'Content-Type': 'application/x-protobuf',
                    'Content-Encoding': 'gzip',
                },
                timeout=self._timeout,
            )
        except Exception as exc:
            warnings.warn(f'Logfire profiling: failed to export profile: {exc!r}')
            return False

        if not (200 <= response.status_code < 300):
            warnings.warn(
                f'Logfire profiling: profile export rejected ({response.status_code}): {response.text[:200]!r}'
            )
            return False
        return True
