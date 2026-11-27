"""Hosted regions and region identification for SDK credentials."""

import re
from typing import TypedDict

LOGFIRE_TOKEN_REGION_PATTERN = re.compile(r'^pylf_v[0-9]+_(?P<region>[a-z]+)_')


class _RegionData(TypedDict):
    base_url: str
    gcp_region: str


REGIONS: dict[str, _RegionData] = {
    'us': {'base_url': 'https://logfire-us.pydantic.dev', 'gcp_region': 'us-east4'},
    'eu': {'base_url': 'https://logfire-eu.pydantic.dev', 'gcp_region': 'europe-west4'},
}
