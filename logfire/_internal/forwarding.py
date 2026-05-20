from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal
from urllib.parse import unquote

OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES = 64 * 1024 * 1024
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024
_MEDIA_TYPE_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+/[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PARAMETER_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+=")
ForwardingPath = Literal['/v1/traces', '/v1/logs', '/v1/metrics']


class ForwardingContentType(Enum):
    PROTOBUF = 'application/x-protobuf'
    JSON = 'application/json'


@dataclass(frozen=True)
class ForwardingRequest:
    path: ForwardingPath
    body: bytes
    content_type: ForwardingContentType
    content_type_header: str
    content_encoding: str | None
    user_agent: str | None


@dataclass(frozen=True)
class ForwardingErrorResponse:
    status_code: int
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ForwardingAdmissionResult:
    response: Literal['success', 'partial_success']
    message: str | None


@dataclass(frozen=True)
class QueuedForwardingRequest:
    request: ForwardingRequest
    tokens: tuple[str, ...]


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name:
            return value
    return None


def parse_forwarding_content_type(headers: Mapping[str, str]) -> ForwardingContentType | None:
    content_type = _get_header(headers, 'content-type')
    if content_type is None:
        return None

    parts = [part.strip() for part in content_type.split(';')]
    media_type = parts[0]
    if not media_type or not _MEDIA_TYPE_RE.fullmatch(media_type):
        return None

    for parameter in parts[1:]:
        if parameter and not _PARAMETER_RE.match(parameter):
            return None

    media_type = media_type.lower()
    if media_type == ForwardingContentType.PROTOBUF.value:
        return ForwardingContentType.PROTOBUF
    if media_type == ForwardingContentType.JSON.value:
        return ForwardingContentType.JSON
    return None


def _invalid_path_response() -> ForwardingErrorResponse:
    return ForwardingErrorResponse(
        status_code=400,
        content_type='text/plain',
        content=b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics',
    )


def _normalize_forwarding_path(path: str) -> ForwardingPath | ForwardingErrorResponse:  # pyright: ignore[reportUnusedFunction]
    if '://' in path or '?' in path or '#' in path:
        return _invalid_path_response()

    if not path.startswith('/'):
        path = '/' + path

    normalized_path = posixpath.normpath(unquote(path))
    if normalized_path == '/v1/traces':
        return '/v1/traces'
    if normalized_path == '/v1/logs':
        return '/v1/logs'
    if normalized_path == '/v1/metrics':
        return '/v1/metrics'
    return _invalid_path_response()
