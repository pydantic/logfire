# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
from __future__ import annotations as _annotations

import os
from typing import Any

from algoliasearch.search_client import SearchClient, SearchIndex
from bs4 import BeautifulSoup
from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

records: list[dict[str, Any]] = []
ALGOLIA_INDEX_NAME = 'logfire-docs'
ALGOLIA_APP_ID = 'KPPUDTIAVX'
ALGOLIA_WRITE_API_KEY = os.environ.get('ALGOLIA_WRITE_API_KEY')


def on_page_content(html: str, page: Page, config: Config, files: Files) -> str:
    if not ALGOLIA_WRITE_API_KEY:
        return html

    title: str = str(page.title)

    soup = BeautifulSoup(html, 'html.parser')

    # Find all h1 and h2 headings
    headings = soup.find_all(['h1', 'h2'])

    # Process each section
    for i in range(len(headings)):
        current_heading = headings[i]
        heading_id = current_heading.get('id', '')
        section_title = current_heading.get_text().replace('¶', '').replace('dataclass', '').strip()

        # Get content until next heading
        content = []
        sibling = current_heading.find_next_sibling()
        while sibling and sibling.name not in ['h1', 'h2']:
            content.append(str(sibling))
            sibling = sibling.find_next_sibling()

        section_html = ''.join(content)

        # Create anchor URL
        anchor_url = f'{page.abs_url}#{heading_id}' if heading_id else page.abs_url

        # Create record for this section
        records.append(
            {
                'content': section_html,
                'pageID': page.title,
                'abs_url': anchor_url,
                'title': f'{title} - {section_title}',
                'objectID': anchor_url,
            }
        )

    return html


def on_post_build(config: Config) -> None:
    if not ALGOLIA_WRITE_API_KEY:
        return

    client = SearchClient.create(ALGOLIA_APP_ID, ALGOLIA_WRITE_API_KEY)
    index: SearchIndex = client.init_index(ALGOLIA_INDEX_NAME)
    # temporary filter the records from the index if the content is bigger than 10k characters
    filtered_records = list(filter(lambda record: len(record['content']) < 9000, records))
    print(f'Uploading {len(filtered_records)} out of {len(records)} records to Algolia...')
    index.replace_all_objects(filtered_records, {'createIfNotExists': True}).wait()
