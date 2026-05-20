"""Tests for `logfire.Artifact` — the JSON-schema/encoder hooks and the blob uploader."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from pathlib import Path
from typing import Any

import pytest
import requests_mock as requests_mock_module

import logfire
from logfire._internal.artifacts import Artifact
from logfire._internal.exporters.artifact_uploader import ArtifactUploader
from logfire._internal.json_encoder import logfire_json_dumps, to_json_value
from logfire._internal.json_schema import create_json_schema
from logfire.testing import TestExporter

_BLOB = b'\x89PNG\r\n\x1a\n' + b'logfire-artifact' * 8
_SHA = hashlib.sha256(_BLOB).hexdigest()


# --- Artifact construction ---


def test_artifact_from_bytes() -> None:
    artifact = Artifact(_BLOB, filename='cat.png', content_type='image/png')
    assert artifact.sha256 == _SHA
    assert artifact.size_bytes == len(_BLOB)
    assert artifact.content_type == 'image/png'
    assert artifact.read() == _BLOB
    assert artifact.reference() == {
        'type': 'logfire.artifact',
        'sha256': _SHA,
        'content_type': 'image/png',
        'size_bytes': len(_BLOB),
        'filename': 'cat.png',
    }


def test_artifact_from_file(tmp_path: Path) -> None:
    path = tmp_path / 'report.pdf'
    path.write_bytes(_BLOB)
    artifact = Artifact.from_file(path)
    assert artifact.sha256 == _SHA
    assert artifact.size_bytes == len(_BLOB)
    assert artifact.filename == 'report.pdf'
    # content type is inferred from the path extension
    assert artifact.content_type == 'application/pdf'
    assert artifact.read() == _BLOB


def test_artifact_from_file_handle() -> None:
    handle = io.BytesIO(_BLOB)
    artifact = Artifact.from_file_handle(handle, filename='audio.mp3')
    # the handle is fully read on construction, so closing it does not lose data
    handle.close()
    assert artifact.sha256 == _SHA
    assert artifact.content_type == 'audio/mpeg'
    assert artifact.read() == _BLOB


def test_artifact_content_type_defaults_to_octet_stream() -> None:
    assert Artifact(_BLOB).content_type == 'application/octet-stream'


def test_artifact_upload_mode_defaults_to_background() -> None:
    assert Artifact(_BLOB).upload == 'background'
    assert Artifact(_BLOB, upload='sync').upload == 'sync'


# --- json_schema / json_encoder hooks ---


def test_artifact_json_schema() -> None:
    assert create_json_schema(Artifact(_BLOB), set()) == {'type': 'object', 'x-python-datatype': 'logfire-artifact'}


def test_artifact_json_encoding() -> None:
    artifact = Artifact(_BLOB, filename='cat.png', content_type='image/png')
    assert to_json_value(artifact, set()) == artifact.reference()
    # round-trips through the full dumps path used for span attributes
    assert json.loads(logfire_json_dumps(artifact)) == artifact.reference()


def test_artifact_logged_as_span_attribute(exporter: TestExporter) -> None:
    """Logging an artifact records the reference object and marks it in the json schema."""
    logfire.info('got a file', file=Artifact(_BLOB, filename='cat.png', content_type='image/png'))

    (span,) = exporter.exported_spans
    attributes = span.attributes or {}
    assert json.loads(attributes['file']) == {  # type: ignore[arg-type]
        'type': 'logfire.artifact',
        'sha256': _SHA,
        'content_type': 'image/png',
        'size_bytes': len(_BLOB),
        'filename': 'cat.png',
    }
    schema = json.loads(attributes['logfire.json_schema'])  # type: ignore[arg-type]
    assert schema['properties']['file'] == {'type': 'object', 'x-python-datatype': 'logfire-artifact'}


# --- ArtifactUploader ---


def _uploader(requests_mock: requests_mock_module.Mocker) -> ArtifactUploader:
    return ArtifactUploader(base_url='http://test', token='write-tok')


def test_uploader_sync_handshake(requests_mock: requests_mock_module.Mocker) -> None:
    """A sync upload runs register -> PUT -> finalize inline."""
    register = requests_mock.post(
        'http://test/v1/artifacts',
        json={
            'sha256': _SHA,
            'status': 'upload',
            'upload': {'method': 'PUT', 'url': f'http://test/v1/artifacts/{_SHA}/blob', 'requires_auth': True},
        },
        status_code=201,
    )
    blob = requests_mock.put(f'http://test/v1/artifacts/{_SHA}/blob', status_code=204)
    finalize = requests_mock.post(f'http://test/v1/artifacts/{_SHA}/finalize', json={}, status_code=200)

    uploader = _uploader(requests_mock)
    uploader.submit(Artifact(_BLOB, upload='sync'))

    assert register.called and blob.called and finalize.called
    assert register.last_request.json()['sha256'] == _SHA  # type: ignore[union-attr]
    # the direct /blob endpoint requires the write token
    assert blob.last_request.headers['Authorization'] == 'Bearer write-tok'  # type: ignore[union-attr]
    assert blob.last_request.body == _BLOB  # type: ignore[union-attr]
    uploader.shutdown()


def test_uploader_dedup_skips_put(requests_mock: requests_mock_module.Mocker) -> None:
    """When the backend reports the content already exists, no blob is uploaded."""
    register = requests_mock.post(
        'http://test/v1/artifacts', json={'sha256': _SHA, 'status': 'exists', 'upload': None}, status_code=201
    )
    blob = requests_mock.put(f'http://test/v1/artifacts/{_SHA}/blob', status_code=204)

    uploader = _uploader(requests_mock)
    uploader.submit(Artifact(_BLOB, upload='sync'))

    assert register.called
    assert not blob.called
    uploader.shutdown()


def test_uploader_signed_url_omits_auth(requests_mock: requests_mock_module.Mocker) -> None:
    """A signed object-store URL must be PUT to without the bearer token."""
    requests_mock.post(
        'http://test/v1/artifacts',
        json={
            'sha256': _SHA,
            'status': 'upload',
            'upload': {'method': 'PUT', 'url': 'http://signed.example/put', 'requires_auth': False},
        },
        status_code=201,
    )
    signed_put = requests_mock.put('http://signed.example/put', status_code=200)
    requests_mock.post(f'http://test/v1/artifacts/{_SHA}/finalize', json={}, status_code=200)

    uploader = _uploader(requests_mock)
    uploader.submit(Artifact(_BLOB, upload='sync'))

    assert signed_put.called
    assert 'Authorization' not in signed_put.last_request.headers  # type: ignore[union-attr]
    uploader.shutdown()


def test_uploader_background_drains_on_flush(requests_mock: requests_mock_module.Mocker) -> None:
    """A background upload completes once `flush` returns."""
    register = requests_mock.post(
        'http://test/v1/artifacts',
        json={
            'sha256': _SHA,
            'status': 'upload',
            'upload': {'method': 'PUT', 'url': f'http://test/v1/artifacts/{_SHA}/blob', 'requires_auth': True},
        },
        status_code=201,
    )
    requests_mock.put(f'http://test/v1/artifacts/{_SHA}/blob', status_code=204)
    finalize = requests_mock.post(f'http://test/v1/artifacts/{_SHA}/finalize', json={}, status_code=200)

    uploader = _uploader(requests_mock)
    uploader.submit(Artifact(_BLOB, upload='background'))
    assert uploader.flush(timeout=5) is True

    assert register.called and finalize.called
    uploader.shutdown()


def test_uploader_swallows_errors(requests_mock: requests_mock_module.Mocker) -> None:
    """A failed upload must never propagate out of `submit` and break the caller."""
    requests_mock.post('http://test/v1/artifacts', status_code=500)

    uploader = _uploader(requests_mock)
    uploader.submit(Artifact(_BLOB, upload='sync'))  # must not raise
    uploader.submit(Artifact(_BLOB, upload='background'))
    assert uploader.flush(timeout=5) is True
    uploader.shutdown()


def test_uploader_background_drops_when_queue_full(requests_mock: requests_mock_module.Mocker) -> None:
    """A `background` submit must never block: when the queue is full the artifact is
    dropped with a warning instead of applying backpressure."""
    release = threading.Event()

    def slow_register(_request: Any, context: Any) -> dict[str, Any]:
        # Hold the worker thread so the first artifact stays counted against the budget.
        release.wait(timeout=5)
        context.status_code = 201
        return {'sha256': _SHA, 'status': 'exists', 'upload': None}

    requests_mock.post('http://test/v1/artifacts', json=slow_register)

    # A 1-byte budget: the first (oversized) artifact is admitted since the queue is
    # empty; while the worker is stuck on it, the second submit overflows and is dropped.
    uploader = ArtifactUploader(base_url='http://test', token='write-tok', max_queue_bytes=1)
    uploader.submit(Artifact(_BLOB, upload='background'))
    with pytest.warns(UserWarning, match='queue is full'):
        uploader.submit(Artifact(_BLOB, upload='background'))

    release.set()
    uploader.shutdown()
