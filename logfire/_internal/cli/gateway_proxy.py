from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class CallRecord:
    ts: float
    route: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class SpendLedger:
    total_usd: float = 0.0
    calls: list[CallRecord] = field(default_factory=list[CallRecord])

    def record(self, record: CallRecord) -> None:
        self.total_usd += record.cost_usd
        self.calls.append(record)
        if len(self.calls) > 200:
            self.calls = self.calls[-200:]

    @property
    def last(self) -> CallRecord | None:
        if not self.calls:
            return None
        return self.calls[-1]


def usage_record_from_response(
    *, route: str, request_body: bytes, response_body: bytes, content_type: str, now: float | None = None
) -> CallRecord | None:
    input_tokens, output_tokens, cost = extract_usage(response_body, content_type)
    if not input_tokens and not output_tokens and not cost:
        return None
    return CallRecord(
        now if now is not None else time.time(),
        route,
        extract_request_model(request_body),
        input_tokens,
        output_tokens,
        cost,
    )


def extract_usage(response_body: bytes, content_type: str) -> tuple[int, int, float]:
    if 'application/json' not in content_type:
        return 0, 0, 0.0
    try:
        parsed = json.loads(response_body)
    except (json.JSONDecodeError, ValueError):
        return 0, 0, 0.0
    if not isinstance(parsed, dict):
        return 0, 0, 0.0
    data = cast(dict[str, Any], parsed)
    usage = data.get('usage')
    if not isinstance(usage, dict):
        return 0, 0, 0.0
    usage_data = cast(dict[str, Any], usage)
    if 'prompt_tokens' in usage or 'completion_tokens' in usage:
        return (
            _usage_int(usage_data, 'prompt_tokens'),
            _usage_int(usage_data, 'completion_tokens'),
            _usage_float(usage_data, 'cost_usd'),
        )
    if 'input_tokens' in usage or 'output_tokens' in usage:
        return (
            _usage_int(usage_data, 'input_tokens'),
            _usage_int(usage_data, 'output_tokens'),
            _usage_float(usage_data, 'cost_usd'),
        )
    return 0, 0, 0.0


def extract_request_model(request_body: bytes) -> str:
    try:
        parsed: Any = json.loads(request_body) if request_body else {}
    except (json.JSONDecodeError, ValueError):
        return ''
    body_json = cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}
    return str(body_json.get('model', ''))


def gateway_status_payload(
    *, region: str, gateway: str, token_ttl_s: float, ledger: SpendLedger, limit_pending: bool
) -> dict[str, Any]:
    last = ledger.last
    return {
        'region': region,
        'gateway': gateway,
        'token_ttl_s': int(token_ttl_s),
        'session_spend_usd': round(ledger.total_usd, 6),
        'limit_pending': limit_pending,
        'last_call': None if last is None else call_record_payload(last),
    }


def claude_status_payload(
    *, region: str, token_ttl_s: float, ledger: SpendLedger, limit_pending: bool
) -> dict[str, Any]:
    return {
        'region': region,
        'spend_usd': round(ledger.total_usd, 6),
        'token_ttl_s': int(token_ttl_s),
        'limit_pending': limit_pending,
        'status_line': f'logfire gateway {region} | ${ledger.total_usd:.2f} | ttl {int(token_ttl_s) // 60}m',
    }


def call_record_payload(record: CallRecord) -> dict[str, Any]:
    return {
        'ts': record.ts,
        'route': record.route,
        'model': record.model,
        'input_tokens': record.input_tokens,
        'output_tokens': record.output_tokens,
        'cost_usd': record.cost_usd,
    }


def _usage_int(usage: dict[str, Any], key: str) -> int:
    try:
        value = int(usage.get(key) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return value if value >= 0 else 0


def _usage_float(usage: dict[str, Any], key: str) -> float:
    try:
        value = float(usage.get(key) or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0
