import json

from logfire import VERSION, info
from logfire.testing import TestExporter


def test_collect_resources(exporter: TestExporter) -> None:
    info('test')

    resources = [span['resource'] for span in exporter.exported_spans_as_dict(include_resources=True)]

    assert len(resources) == 1
    resource = resources[0]
    data = json.loads(resource['attributes']['logfire.package_versions'])

    assert {'name': 'logfire', 'version': VERSION} in data and len(data) > 1
