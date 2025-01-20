from __future__ import annotations as _annotations

import os
from typing import Any, cast

from algoliasearch.search_client import SearchClient
from bs4 import BeautifulSoup
from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

records: list[dict[str, Any]] = []
ALGOLIA_INDEX_NAME = 'logfire-docs'
ALGOLIA_APP_ID = 'KPPUDTIAVX'
ALGOLIA_WRITE_API_KEY = os.environ.get('ALGOLIA_WRITE_API_KEY')
# Algolia accepts 100k, leaaving some room for other fields
MAX_CONTENT_SIZE = 90_000


def on_page_content(html: str, page: Page, config: Config, files: Files) -> str:
    if not ALGOLIA_WRITE_API_KEY:
        return html

    assert page.title is not None, 'Page title must not be None'  # type: ignore[reportUnknownMemberType]
    title = cast(str, page.title)  # type: ignore[reportUnknownMemberType]

    soup = BeautifulSoup(html, 'html.parser')

    # Clean up presentational and UI elements
    for element in soup.find_all(['autoref']):
        element.decompose()

    # this removes the large source code embeds from Github
    for element in soup.find_all('details'):
        element.decompose()

    for el_with_class in soup.find_all(class_=['doc-section-item', 'doc-section-title', 'doc-md-description', 'doc']):
        # delete the class attribute
        del el_with_class['class']

    # Cleanup code examples
    for extra in soup.find_all('div', attrs={'class': ['language-py highlight', 'language-python highlight']}):
        extra.replace_with(BeautifulSoup(f'<pre>{extra.find("code").get_text()}</pre>', 'html.parser'))

    # Cleanup code examples, part 2
    for extra in soup.find_all('div', attrs={'class': 'language-python doc-signature highlight'}):
        extra.replace_with(BeautifulSoup(f'<pre>{extra.find("code").get_text()}</pre>', 'html.parser'))

    # The API reference generates HTML tables with line numbers, this strips the line numbers cell and goes back to a code block
    for extra in soup.find_all('table', attrs={'class': 'highlighttable'}):
        extra.replace_with(BeautifulSoup(f'<pre>{extra.find("code").get_text()}</pre>', 'html.parser'))

    # Find all h1 and h2 headings
    headings = soup.find_all(['h1', 'h2'])

    # Process each section
    for i in range(len(headings)):
        current_heading = headings[i]
        heading_id = current_heading.get('id', '')
        section_title = current_heading.get_text().replace('¶', '').replace('dataclass', '').strip()

        # Get content until next heading
        content: list[str] = []
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
                'pageID': title,
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
    index = client.init_index(ALGOLIA_INDEX_NAME)

    for large_record in list(filter(lambda record: len(record['content']) >= MAX_CONTENT_SIZE, records)):
        print(f'Content for {large_record["abs_url"]} is too large to be indexed. Skipping...')
        print(f'Content : {large_record["content"]} characters')

    # filter the records from the index if the content is bigger than 10k characters
    filtered_records = list(filter(lambda record: len(record['content']) < MAX_CONTENT_SIZE, records))
    print(f'Uploading {len(filtered_records)} out of {len(records)} records to Algolia...')
    index.replace_all_objects(filtered_records, {'createIfNotExists': True}).wait()  # type: ignore[reportUnknownMemberType]
