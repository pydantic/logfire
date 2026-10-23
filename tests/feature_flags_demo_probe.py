"""Drive the real demo in an isolated process with HTTP/SSE fault injection."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests
import uvicorn
from openfeature import api
from openfeature.provider.no_op_provider import NoOpProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, Sum
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import TestExporter
from logfire.variables.config import LabeledValue, VariablesConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.python.feature_flags_demo import create_app, demo_config

TOKEN = 'pylf_v1_us_demo_not_a_real_key'


class DeliveryServer:
    def __init__(self, *, unavailable: bool):
        self.condition = threading.Condition()
        self.config = demo_config().model_dump(mode='json')
        self.revision = 1
        self.status = 503 if unavailable else 200
        self.stopping = False
        self.stream_generation = 0
        self.connections = 0
        self.polls: list[tuple[int, str | None]] = []
        self.authorization: list[str | None] = []
        controller = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self) -> None:
                with controller.condition:
                    controller.authorization.append(self.headers.get('Authorization'))
                if self.path == '/v1/variable-updates/':
                    self.stream()
                    return
                assert self.path == '/v1/variables/', self.path
                with controller.condition:
                    etag = f'"{controller.revision}"'
                    status = controller.status
                    if status == 200 and self.headers.get('If-None-Match') == etag:
                        status = 304
                    body = json.dumps(controller.config).encode() if status == 200 else b''
                    controller.polls.append((status, self.headers.get('If-None-Match')))
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('ETag', etag)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def stream(self) -> None:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                with controller.condition:
                    revision = controller.revision
                    generation = controller.stream_generation
                    controller.connections += 1
                    controller.condition.notify_all()
                try:
                    while True:
                        with controller.condition:
                            if controller.stopping or generation != controller.stream_generation:
                                break
                            changed = revision != controller.revision
                            revision = controller.revision
                        event = 'data: {"event":"updated"}\n\n' if changed else ': keepalive\n\n'
                        # Padding makes requests' default 512-byte streaming buffer deliver immediately.
                        chunk = (': ' + ' ' * 512 + '\n' + event).encode()
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                        self.wfile.flush()
                        with controller.condition:
                            controller.condition.wait(timeout=0.05)
                    self.wfile.write(b'0\r\n\r\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.server.server_port}'

    def publish(self, config: VariablesConfig | dict[str, Any], *, status: int = 200, disconnect: bool = False) -> None:
        with self.condition:
            self.config = config.model_dump(mode='json') if isinstance(config, VariablesConfig) else config
            self.status = status
            self.revision += 1
            if disconnect:
                self.stream_generation += 1
            self.condition.notify_all()

    def close(self) -> None:
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        assert not self.thread.is_alive()


def eventually(check: Callable[[], bool], description: str) -> None:
    deadline = time.monotonic() + 8
    while not check():
        assert time.monotonic() < deadline, description
        time.sleep(0.02)


@contextmanager
def serving(app: Any):
    # Keep the ephemeral port reserved until Uvicorn adopts it; no free-port race.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='on'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            eventually(lambda: server.started, 'demo did not start')
            yield f'http://127.0.0.1:{port}'
        finally:
            server.should_exit = True
            thread.join(8)
            assert not thread.is_alive(), 'demo did not shut down'


def main(scenario: str, *, wait_for_recovery_poll: bool = False) -> None:
    if scenario == 'lifecycle':
        client = api.get_client(domain='support-demo')
        previous = client.provider
        default = api.get_client().provider
        unrelated = NoOpProvider()
        api.set_provider_and_wait(unrelated, domain='unrelated-demo')
        for _ in range(2):
            with serving(create_app()) as url:
                response = requests.post(
                    url + '/support', json={'customer_id': 'example-account', 'plan': 'team'}, timeout=5
                )
                assert response.status_code == 200, response.text
                assert response.json()['assisted'] is True
                assert client.provider is not previous
            assert client.provider is previous, 'app left its stopped provider registered'
            assert client.get_boolean_value('citations', False) is False
            assert api.get_client().provider is default
            assert api.get_client(domain='unrelated-demo').provider is unrelated

        replacement = NoOpProvider()
        with serving(create_app()):
            api.set_provider_and_wait(replacement, domain='support-demo')
        assert client.provider is replacement, 'teardown overwrote a newer provider'
        assert api.get_client().provider is default
        assert api.get_client(domain='unrelated-demo').provider is unrelated
        print(json.dumps({'scenario': scenario, 'requests': 2, 'domains_preserved': True}))
        return

    if scenario == 'local':
        with serving(create_app()) as url:
            for plan, enabled in (('team', True), ('free', False)):
                response = requests.post(
                    url + '/support', json={'customer_id': 'example-account', 'plan': plan}, timeout=5
                )
                assert response.status_code == 200, response.text
                result = response.json()
                assert result['assisted'] is enabled
                assert result['assisted_before_yield'] is enabled
                assert result['model'] == 'large'
                assert result['max_documents'] == 3
                assert result['reply_budget'] == 256
                assert result['prompt'] == 'Help Acme customers with installation.'
        assert not any(thread.name.startswith('LogfireRemoteProvider') for thread in threading.enumerate())
        print(json.dumps({'scenario': scenario, 'requests': 2, 'clean_shutdown': True}))
        return

    delivery = DeliveryServer(unavailable=scenario == 'cold-start')
    delivery.thread.start()
    exporter = TestExporter()
    metrics = InMemoryMetricReader()
    sdk = logfire.configure(
        local=True,
        send_to_logfire=False,
        console=False,
        api_key=TOKEN,
        advanced=logfire.AdvancedOptions(base_url=delivery.url),
        variables=logfire.VariablesOptions(polling_interval=600, timeout=(1, 1)),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        metrics=logfire.MetricsOptions(additional_readers=[metrics]),
    )
    completed = 0
    completed_lock = threading.Lock()
    sdk_stopped = False
    phases: list[str] = []
    try:
        with serving(create_app(sdk)) as url:

            def support(index: int = 0, plan: str = 'team') -> dict[str, Any]:
                nonlocal completed
                response = requests.post(
                    url + '/support',
                    json={'customer_id': f'customer-private-{index}', 'plan': plan, 'topic': 'installation'},
                    timeout=5,
                )
                assert response.status_code == 200, response.text
                with completed_lock:
                    completed += 1
                return response.json()

            eventually(lambda: delivery.connections > 0, 'SSE connection was not established')
            if scenario == 'cold-start':
                cold = support()
                assert cold['assisted'] is False
                assert cold['model'] == 'small'
                assert cold['max_documents'] == 1
                assert cold['reply_budget'] == 64
                assert cold['budget_error'] is not None
                assert cold['sources'] == ['docs']
                assert cold['banner'] is None
                assert cold['layout'] == 'compact'
                assert cold['prompt'] == 'Help with installation.'
                assert cold['citations'] is False
                assert cold['voice'] == 'neutral'
                assert cold['temperature'] == 0.0
                assert cold['tool_options'] == {}
                phases.append('safe startup during outage')
                delivery.publish(demo_config())

            eventually(lambda: support()['reply_budget'] == 256, 'initial configuration did not load')
            initial = support()
            assert initial['assisted'] is True
            assert initial['assist_reason'] == 'targeting_match'
            assert initial['model'] == 'large'
            assert initial['max_documents'] == 3
            assert initial['sources'] == ['docs', 'tickets']
            assert initial['banner'] == 'How can we help?'
            assert initial['prompt'] == 'Help Acme customers with installation.'
            assert initial['citations'] is True
            assert initial['voice'] == 'friendly'
            assert initial['reply_budget'] == initial['alias_budget'] == 256
            assert initial['temperature'] == 0.2
            assert initial['tool_options'] == {'search': True, 'timeout': 2}
            assert initial['layout_reason'] == 'split'
            phases.append('all value types, targeting, alias, and composed prompt')

            with delivery.condition:
                initial_polls = len(delivery.polls)

            def evaluation_count() -> int:
                return sum(
                    span.name == 'feature_flag.evaluation'
                    and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
                    for span in exporter.exported_spans
                )

            initial_evaluations = evaluation_count()

            if wait_for_recovery_poll:
                # Let the real, scheduled SSE follow-up land inside the measured cache window.
                # This reproduces slow CI without an arbitrary sleep or changing SDK internals.
                assert scenario == 'cold-start'

                def recovery_poll_arrived() -> bool:
                    with delivery.condition:
                        return len(delivery.polls) > initial_polls

                eventually(recovery_poll_arrived, 'scheduled recovery revalidation did not arrive')

            # Repeated customer identities must keep their assignment across interleaved requests.
            def request(index: int) -> tuple[int, dict[str, Any]]:
                return index, support(index % 16, 'free' if index % 2 else 'team')

            with ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(request, range(160)))
            assignments: dict[int, tuple[str, str]] = {}
            for index, result in results:
                assert result['assisted'] is (index % 2 == 0)
                # Only compare decisions while configuration is fixed: a live update between
                # reads can legitimately change a decision without losing the request context.
                assert result['assisted_before_yield'] is result['assisted']
                assignment = result['layout'], result['variant']
                assert assignments.setdefault(index % 16, assignment) == assignment
            with delivery.condition:
                cache_phase_polls = delivery.polls[initial_polls:]
                recovery_revalidation = (304, f'"{delivery.revision}"')
            # The unchanged live scenario must make no requests. Recovery deliberately schedules
            # one conditional revalidation after 2s, which may overlap a slow request batch.
            # Permit only that one 304 with the current validator, never arbitrary extra fetches.
            assert not cache_phase_polls or (
                scenario == 'cold-start' and cache_phase_polls == [recovery_revalidation]
            ), cache_phase_polls
            if wait_for_recovery_poll:
                assert cache_phase_polls == [recovery_revalidation]
            # Each read emits exactly once; the emergency flag is short-circuited for free users.
            assert evaluation_count() - initial_evaluations == 80 * 14 + 80 * 13
            phases.append('160 concurrent requests: stable assignments, isolated contexts, no per-request fetches')

            # Explicit revalidation should transfer no body when the cached version is current.
            sdk.variables_pull_config()
            with delivery.condition:
                assert delivery.polls[-1] == (304, f'"{delivery.revision}"')
            assert support()['reply_budget'] == 256
            phases.append('ETag revalidation preserves cached values')

            # No refresh API is called: every transition below must arrive via SSE or reconnect.
            config = demo_config()
            config.variables['agent_policy'].labels['live'] = LabeledValue(
                version=2, serialized_value='{"model":"large","max_documents":7}'
            )
            config.variables['brand'].labels['live'] = LabeledValue(version=2, serialized_value='"Acme Two"')
            delivery.publish(config)
            eventually(lambda: support()['max_documents'] == 7, 'SSE update was not applied')
            assert support()['prompt'] == 'Help Acme Two customers with installation.'
            phases.append('live policy and composition updates')

            invalid = config.model_copy(deep=True)
            invalid.variables['agent_policy'].labels['live'] = LabeledValue(
                version=3,
                serialized_value='{"model":"large","max_documents":0,"api_key":"demo-invalid-credential"}',
            )
            invalid.variables['reply_budget'].labels['live'] = LabeledValue(version=3, serialized_value='true')
            delivery.publish(invalid)
            eventually(lambda: support()['policy_error'] == 'type_mismatch', 'invalid policy was not rejected')
            invalid_result = support()
            assert invalid_result['model'] == 'small'
            assert invalid_result['max_documents'] == 1
            assert invalid_result['reply_budget'] == 64
            assert invalid_result['budget_error'] == 'TYPE_MISMATCH'
            phases.append('invalid Pydantic policy and boolean-as-integer safely fall back')

            delivery.publish(config)
            eventually(lambda: support()['max_documents'] == 7, 'valid configuration did not recover')
            delivery.publish(config, status=503)
            eventually(lambda: support()['assist_reason'] == 'stale', 'outage did not mark cached values stale')
            stale = support()
            assert stale['assisted'] is True
            assert stale['max_documents'] == 7
            assert stale['reply_budget'] == 256
            assert stale['budget_reason'] == 'STALE'
            phases.append('outage retains last loaded values and reports staleness')

            delivery.publish(config)
            eventually(lambda: support()['assist_reason'] == 'targeting_match', 'outage did not recover')

            delivery.publish({'variables': None})
            eventually(lambda: support()['assist_reason'] == 'stale', 'malformed configuration was not rejected')
            assert support()['max_documents'] == 7
            delivery.publish(config)
            eventually(
                lambda: support()['assist_reason'] == 'targeting_match', 'malformed configuration did not recover'
            )
            phases.append('malformed configuration retains the last loaded snapshot and recovers')

            with delivery.condition:
                connections = delivery.connections
            config.variables['agent_policy'].labels['live'] = LabeledValue(
                version=4, serialized_value='{"model":"large","max_documents":9}'
            )
            delivery.publish(config, disconnect=True)
            eventually(lambda: support()['max_documents'] == 9, 'reconnect did not reconcile missed update')
            assert delivery.connections > connections
            phases.append('SSE reconnect reconciles an update without receiving its event')

            del config.variables['banner']
            del config.variables['reply_budget']
            delivery.publish(config)
            eventually(lambda: support()['budget_error'] == 'FLAG_NOT_FOUND', 'deleted flag remained cached')
            deleted = support()
            assert deleted['banner'] is None
            assert deleted['reply_budget'] == deleted['alias_budget'] == 64
            phases.append('deletion and removed aliases return safe defaults')

            bad_request = requests.post(url + '/support', json={'plan': 'not-a-plan'}, timeout=5)
            assert bad_request.status_code == 422
            assert support(plan='free')['assisted'] is False

            data = metrics.get_metrics_data()
            assert data is not None
            total = sum(
                point.value
                for resource in data.resource_metrics
                for scope in resource.scope_metrics
                for metric in scope.metrics
                if metric.name == 'support.requests'
                if isinstance(metric.data, Sum)
                for point in metric.data.data_points
            )
            assert total == completed, (total, completed)
            phases.append('request counter agrees with completed HTTP requests')

        sdk.shutdown()
        sdk_stopped = True
        spans = [
            span
            for span in exporter.exported_spans
            if (span.attributes or {}).get('logfire.span_type') != 'pending_span'
        ]
        evaluations = [span for span in spans if span.name == 'feature_flag.evaluation']
        assert len(evaluations) >= 1_500
        declarations = Counter(
            str((span.attributes or {})['logfire.variable.name'])
            for span in spans
            if (span.attributes or {}).get('logfire.variable.declaration')
        )
        assert set(declarations) == {
            'assist_enabled',
            'agent_policy',
            'layout',
            'sources',
            'banner',
            'brand',
            'emergency_shutdown',
            'support_prompt',
        }, declarations
        assert set(declarations.values()) == {1}, declarations
        assert {variable.name for variable in sdk.variables_get()} == set(declarations)
        # The targeting key is recorded as `feature_flag.context.id` by design. Every other attribute,
        # including the targeting attributes, must keep customer identifiers and credentials out.
        context_ids = {
            str(context_id)
            for span in evaluations
            if (context_id := (span.attributes or {}).get('feature_flag.context.id')) is not None
        }
        assert context_ids and all(value.startswith('customer-private-') for value in context_ids), context_ids
        serialized = repr(
            [
                {key: value for key, value in (span.attributes or {}).items() if key != 'feature_flag.context.id'}
                for span in spans
            ]
        )
        for secret in (
            'customer-private-',
            'demo-local-credential',
            'demo-remote-credential',
            'demo-invalid-credential',
            TOKEN,
        ):
            assert secret not in serialized, [
                (span.name, key, value)
                for span in spans
                for key, value in (span.attributes or {}).items()
                if secret in repr(value)
            ][:5]
        assert any(span.name == 'POST /support' for span in spans)
        assert all(value == f'bearer {TOKEN}' for value in delivery.authorization)
        assert any(status == 304 for status, _ in delivery.polls), 'conditional revalidation was not exercised'
        assert not any(thread.name.startswith('LogfireRemoteProvider') for thread in threading.enumerate())
        print(
            json.dumps(
                {
                    'scenario': scenario,
                    'requests': completed,
                    'flag_evaluations': len(evaluations),
                    'configuration_requests': len(delivery.polls),
                    'cache_phase_revalidations': len(cache_phase_polls),
                    'sse_connections': delivery.connections,
                    'declarations': len(declarations),
                    'telemetry_private': True,
                    'clean_shutdown': True,
                    'phases': phases,
                }
            )
        )
    finally:
        if not sdk_stopped:
            sdk.shutdown()
        delivery.close()


if __name__ == '__main__':
    main(sys.argv[1], wait_for_recovery_poll='--wait-for-recovery-poll' in sys.argv[2:])
