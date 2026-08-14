import json
from typing import Any, NamedTuple

from elastic_transport import ApiResponseMeta, BaseNode, HttpHeaders
from elasticsearch import Elasticsearch
from inline_snapshot import snapshot

from logfire.testing import TestExporter


class OfflineNodeResponse(NamedTuple):
    """Public tuple protocol returned by ``BaseNode.perform_request()``."""

    meta: ApiResponseMeta
    body: bytes


RESPONSE_DICT: dict[str, Any] = {
    'took': 1,
    'timed_out': False,
    '_shards': {'total': 1, 'successful': 1, 'skipped': 0, 'failed': 0},
    'hits': {'total': {'value': 0, 'relation': 'eq'}, 'max_score': None, 'hits': []},
}


class OfflineNode(BaseNode):
    """Return an Elasticsearch response without making a network request."""

    def perform_request(
        self,
        method: str,
        target: str,
        body: bytes | None = None,
        headers: HttpHeaders | None = None,
        request_timeout: Any = None,
    ) -> Any:
        del method, target, body, headers, request_timeout
        meta = ApiResponseMeta(
            status=200,
            http_version='1.1',
            headers=HttpHeaders(
                {
                    'content-type': 'application/json',
                    'x-elastic-product': 'Elasticsearch',
                }
            ),
            duration=0.001,
            node=self.config,
        )
        response = json.dumps(RESPONSE_DICT).encode()
        # `BaseNode.perform_request()` documents this public tuple protocol even
        # though elastic-transport's concrete return type is private.
        return OfflineNodeResponse(meta, response)


def test_native_elasticsearch_instrumentation(exporter: TestExporter) -> None:
    client = Elasticsearch('http://localhost:9200', node_class=OfflineNode)

    response = client.search(index='products', query={'match': {'name': 'coffee'}})

    assert response == RESPONSE_DICT
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans == snapshot(
        [
            {
                'name': 'search',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'search',
                    'db.operation.parameter.index': 'products',
                    'db.system.name': 'elasticsearch',
                    'db.operation.name': 'search',
                    'url.full': 'http://localhost:9200/products/_search',
                    'http.request.method': 'POST',
                    'server.address': 'localhost',
                    'server.port': 9200,
                    'db.response.status_code': '200',
                },
            }
        ]
    )
