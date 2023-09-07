from collections.abc import Sequence

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter

from logfire import LogfireConfig, Observe
from logfire._observe import LogfireClient
from logfire.credentials import LogfireCredentials


class TestExporter(SpanExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans = list(spans)


class TestLogfireClient(LogfireClient):
    # This class exists to eliminate the network requests during testing
    def print_dashboard_url(self) -> None:
        # Do nothing
        return None


class TestLogfireConfig(LogfireConfig):
    # This class exists to eliminate the network requests during testing
    def request_new_project_credentials(self, project_id: str | None) -> LogfireCredentials:
        # Pretend this is what the backend returned
        return LogfireCredentials(project_id=project_id or 'test-project-id', token='test-token')

    def get_client(self) -> 'LogfireClient':
        creds = self.get_credentials()

        return TestLogfireClient(
            api_root=self.api_root,
            service_name=self.service_name,
            project_id=creds.project_id,
            token=creds.token,
            verbose=self.verbose,
        )


@pytest.fixture
def config() -> LogfireConfig:
    return TestLogfireConfig()


@pytest.fixture
def exporter() -> TestExporter:
    return TestExporter()


@pytest.fixture
def observe(config: LogfireConfig, exporter: TestExporter) -> Observe:
    observe = Observe()
    observe.configure(config=config, exporter=exporter)
    return observe
