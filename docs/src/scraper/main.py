import asyncio
import base64
import json
from pathlib import Path

from bs4 import BeautifulSoup
from httpx import AsyncClient

import logfire

START_URL = 'https://github.com/pydantic/pydantic/network/dependents'
CACHE_DIR = Path('cache')
CACHE_DIR.mkdir(exist_ok=True)
REPOS: dict[str, int] = {}


async def get(client: AsyncClient, url: str) -> str:
    file_path = CACHE_DIR / f'get_{base64.urlsafe_b64encode(url.encode()).decode()}.html'
    if file_path.exists():
        return file_path.read_text()
    else:
        logfire.debug('Cache miss {url=}', url=url)
        await asyncio.sleep(1)
        r = await client.get(url)
        if r.status_code != 200:
            logfire.error('Response error with {status_code=}', status_code=r.status_code, text=r.text)
            raise RuntimeError(f'{r.status_code} from {url}')

        ct = r.headers['content-type']
        assert ct.startswith('text/html'), f'Unexpected mimetype: {ct!r} from {url}'

        file_path.write_text(r.text)
        return r.text


@logfire.instrument('get_dependents {url=}')
async def get_dependents(client: AsyncClient, url: str) -> str | None:
    html = await get(client, url)
    soup = BeautifulSoup(html, 'html.parser')

    repos = {}

    for a in soup.find_all('div', {'class': 'Box-row'}):
        user_org = a.find('a', {'data-hovercard-type': 'user'}) or a.find('a', {'data-hovercard-type': 'organization'})
        repo = a.find('a', {'data-hovercard-type': 'repository'})
        star = a.find('svg', {'class': 'octicon-star'}).parent
        star_text = star.getText().strip().replace(',', '')

        repos[f'{user_org.getText()}/{repo.getText()}'] = int(star_text)

    REPOS.update(repos)

    next_link = soup.find('a', string='Next', href=True)
    if next_link:
        return next_link['href']


async def main():
    i = 0
    next_url = START_URL
    try:
        async with AsyncClient() as client:
            while next_url:
                next_url = await get_dependents(client, next_url)
                i += 1

    finally:
        if REPOS:
            repos_path = Path('repos.json')
            logfire.info(
                'Saving {total_repos=} new repos to {repos_path=}...', total_repos=len(REPOS), repos_path=repos_path
            )
            if repos_path.exists():
                with repos_path.open('r') as f:
                    existing_repos = json.load(f)
            else:
                existing_repos: dict[str, int] = {}

            existing_repos.update(REPOS)
            existing_repos = dict(sorted(existing_repos.items(), key=lambda x: x[1], reverse=True))
            logfire.info('Total of {total_repos=} repos', total_repos=len(existing_repos))
            with repos_path.open('w') as f:
                json.dump(existing_repos, f, indent=2)


if __name__ == '__main__':
    asyncio.run(main())
