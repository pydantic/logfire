from __future__ import annotations

import argparse

from opentelemetry._logs import SeverityNumber, get_logger

import logfire
from logfire._internal.config import LogfireConfig


def _skip_credentials_check(self: LogfireConfig, token: str) -> None:
    del self, token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()

    # Credential validation is a separate HTTP API concern. Keep this process focused on the
    # exporter path so its background request cannot race the transport scenario.
    LogfireConfig._initialize_credentials_from_token = _skip_credentials_check  # pyright: ignore[reportPrivateUsage]

    logfire.configure(
        send_to_logfire=True,
        token='collector-conformance-token',
        service_name='logfire-collector-conformance',
        console=False,
        inspect_arguments=False,
        advanced=logfire.AdvancedOptions(base_url=args.endpoint),
    )

    with logfire.span('collector.conformance.parent', **{'test.run_id': args.run_id}):
        logfire.info('collector conformance log', **{'test.run_id': args.run_id})
        get_logger('collector.conformance').emit(
            body='collector conformance otel log',
            severity_text='INFO',
            severity_number=SeverityNumber.INFO,
            attributes={'test.run_id': args.run_id},
        )

    counter = logfire.metric_counter('collector.conformance.counter', unit='1')
    counter.add(7, {'test.run_id': args.run_id})

    if not logfire.force_flush(timeout_millis=10_000):
        raise RuntimeError('Logfire force_flush timed out')
    if not logfire.shutdown(timeout_millis=10_000):
        raise RuntimeError('Logfire shutdown timed out')


if __name__ == '__main__':
    main()
