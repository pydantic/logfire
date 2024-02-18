import json

from dirty_equals import IsPartialDict

from logfire import VERSION, info
from logfire.testing import TestExporter


def test_collect_resources(exporter: TestExporter) -> None:
    info('test')

    resources = [
        span['resource']
        for span in exporter.exported_spans_as_dict(include_resources=True, include_package_versions=True)
    ]

    assert len(resources) == 1
    resource = resources[0]
    data = json.loads(resource['attributes']['logfire.package_versions'])

    assert data == IsPartialDict({'logfire': VERSION})
