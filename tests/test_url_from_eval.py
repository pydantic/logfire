from __future__ import annotations

import pytest

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


def test_url_from_eval_no_ids() -> None:
    config = LogfireConfig(send_to_logfire=False, console=False)
    config.project_url = 'https://logfire.pydantic.dev/my-org/my-project'
    instance = logfire.Logfire(config=config)

    report = _make_report()
    result = instance.url_from_eval(report)
    assert result is None
