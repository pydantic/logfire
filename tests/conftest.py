import pytest

from logfire.observe import Observe


class TestExporter:
    def __init__(self):
        self.exported_spans = []

    def export(self, spans) -> None:
        self.exported_spans = spans

    def shutdown(self) -> None:
        pass


@pytest.fixture
def exporter():
    return TestExporter()


@pytest.fixture
def observe(exporter):
    observe = Observe()
    observe.configure(exporter=exporter)
    return observe
