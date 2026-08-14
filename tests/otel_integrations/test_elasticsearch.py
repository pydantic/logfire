from typing import Any, NamedTuple

from elastic_transport import ApiResponseMeta, BaseNode, HttpHeaders
from elasticsearch import Elasticsearch

from logfire._internal.exporters.test import TestExporter


class OfflineNodeResponse(NamedTuple):
    """Public tuple protocol returned by ``BaseNode.perform_request()``."""

    meta: ApiResponseMeta
    body: bytes


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
        response = (
            b'{"took":1,"timed_out":false,'
            b'"_shards":{"total":1,"successful":1,"skipped":0,"failed":0},'
            b'"hits":{"total":{"value":0,"relation":"eq"},"max_score":null,"hits":[]}}'
        )
        # `BaseNode.perform_request()` documents this public tuple protocol even
        # though elastic-transport's concrete return type is private.
        return OfflineNodeResponse(meta, response)


def test_native_elasticsearch_instrumentation(exporter: TestExporter) -> None:
    client = Elasticsearch('http://localhost:9200', node_class=OfflineNode)

    response = client.search(index='products', query={'match': {'name': 'coffee'}})

    assert response['hits']['total']['value'] == 0
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert spans[0]['name'] == 'search'
    attributes = spans[0]['attributes']
    assert attributes['logfire.msg'] == 'search'
    assert attributes['http.request.method'] == 'POST'
    assert attributes['url.full'] == 'http://localhost:9200/products/_search'
    assert attributes.get('db.system.name', attributes.get('db.system')) == 'elasticsearch'
