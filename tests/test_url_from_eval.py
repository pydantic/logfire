from __future__ import annotations

from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
import requests_mock

try:
    from pydantic_evals.reporting import EvaluationReport
except Exception:
    pytest.skip('pydantic_evals not importable (likely pydantic < 2.8)', allow_module_level=True)

import logfire
from logfire._internal.config import LogfireConfig


def _make_report(trace_id: str | None = None, span_id: str | None = None) -> EvaluationReport:
    return EvaluationReport(name='test', cases=[], trace_id=trace_id, span_id=span_id)


def test_url_from_eval_with_project_url() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project'
    instance = logfire.Logfire(config=config)

    report = _make_report(trace_id='abc123', span_id='def456')
    result = instance.url_from_eval(report)
    assert result == 'https://logfire.pydantic.dev/my-org/my-project/evals/compare?experiment=abc123-def456'


def test_url_from_eval_no_project_url() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    instance = logfire.Logfire(config=config)

    report = _make_report(trace_id='abc123', span_id='def456')
    result = instance.url_from_eval(report)
    assert result is None


def test_url_from_eval_no_trace_id() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project'
    instance = logfire.Logfire(config=config)

    report = _make_report(span_id='def456')
    result = instance.url_from_eval(report)
    assert result is None


def test_url_from_eval_no_span_id() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project'
    instance = logfire.Logfire(config=config)

    report = _make_report(trace_id='abc123')
    result = instance.url_from_eval(report)
    assert result is None


def test_url_from_eval_trailing_slash() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project/'
    instance = logfire.Logfire(config=config)

    report = _make_report(trace_id='abc123', span_id='def456')
    result = instance.url_from_eval(report)
    assert result == 'https://logfire.pydantic.dev/my-org/my-project/evals/compare?experiment=abc123-def456'


def test_url_from_eval_no_ids() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project'
    instance = logfire.Logfire(config=config)

    report = _make_report()
    result = instance.url_from_eval(report)
    assert result is None


def test_reconfigure_discards_stale_project_url(tmp_path: Path) -> None:
    """Test that a background thread from a previous configure() call
    does not write a stale project_url after reconfigure() bumps the generation."""
    block = Event()
    first_thread_done = Event()
    original_from_token = LogfireConfig._initialize_credentials_from_token  # pyright: ignore[reportPrivateUsage]

    call_count = 0

    def slow_from_token(self: LogfireConfig, token: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First configure's thread blocks here until we release it
            block.wait()
            result = original_from_token(self, token)
            first_thread_done.set()
            return result
        return original_from_token(self, token)

    with (
        requests_mock.Mocker() as mocker,
        patch.object(LogfireConfig, '_initialize_credentials_from_token', slow_from_token),
    ):
        mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={
                'project_name': 'stale',
                'project_url': 'https://logfire-us.pydantic.dev/stale-org/stale-project',
            },
        )
        config = LogfireConfig(
            send_to_logfire=True,
            token=['token-a', 'token-a2'],
            console=False,
            data_dir=tmp_path,
        )
        config.initialize()
        first_thread = config._check_tokens_thread  # pyright: ignore[reportPrivateUsage]
        assert first_thread is not None
        # First thread is now blocked in slow_from_token.
        # Reconfigure the same config object - this bumps the generation.
        config.configure(
            send_to_logfire=False,
            token=None,
            api_key=None,
            service_name=None,
            service_version=None,
            environment=None,
            console=False,
            config_dir=None,
            data_dir=tmp_path,
            additional_span_processors=None,
            metrics=None,
            scrubbing=None,
            inspect_arguments=None,
            sampling=None,
            min_level=None,
            add_baggage_to_attributes=True,
            code_source=None,
            variables=None,
            distributed_tracing=None,
            advanced=None,
        )
        # Release the first thread
        block.set()
        assert first_thread_done.wait(timeout=5)
        first_thread.join(timeout=5)
        assert not first_thread.is_alive()
        # The stale thread should NOT have written its project_url
        assert config.project_url is None


def test_url_from_eval_waits_for_token_validation(tmp_path: Path) -> None:
    """Test that url_from_eval waits for the background token validation thread
    to populate project_url when the token is provided directly (no creds file)."""
    with requests_mock.Mocker() as mocker:
        mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={
                'project_name': 'myproject',
                'project_url': 'https://logfire-us.pydantic.dev/my-org/my-project',
            },
        )
        logfire.configure(
            send_to_logfire=True,
            token='fake-token',
            console=False,
            data_dir=tmp_path,
        )

        report = _make_report(trace_id='abc123', span_id='def456')
        # url_from_eval should wait for the background thread and return the URL
        result = logfire.url_from_eval(report)
        assert result == 'https://logfire-us.pydantic.dev/my-org/my-project/evals/compare?experiment=abc123-def456'
