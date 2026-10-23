from __future__ import annotations

import json
import sys
from time import time

import requests
from packaging.version import Version

from ...version import VERSION
from ..auth import HOME_LOGFIRE
from ..http_transport import install_connection_policy
from ..interactive import is_non_interactive


def check_for_updates() -> None:
    """Show newer releases, caching successful checks for a week and failures for a day."""
    if is_non_interactive() or not sys.stderr.isatty():
        return

    now = time()
    cache_path = HOME_LOGFIRE / 'version_check.json'
    latest_version: Version | None = None
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if 'last_failed' in cache and 0 <= now - cache['last_failed'] < 24 * 60 * 60:
            return
        if 0 <= now - cache['last_checked'] < 7 * 24 * 60 * 60:
            latest_version = Version(cache['latest_version'])
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass

    if latest_version is None:
        cache_data: dict[str, float | str] = {'last_failed': now}
        try:
            with requests.Session() as session:
                install_connection_policy(session)
                response = session.get('https://pypi.org/pypi/logfire/json', timeout=1)
                response.raise_for_status()
                latest_version = Version(response.json()['info']['version'])
        except (requests.RequestException, ValueError, KeyError, TypeError, RecursionError):
            pass
        else:
            cache_data = {'last_checked': now, 'latest_version': str(latest_version)}
        try:
            HOME_LOGFIRE.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache_data), encoding='utf-8')
        except OSError:
            pass

    if latest_version is not None and latest_version > Version(VERSION):
        sys.stderr.write(
            f'Logfire {latest_version} is available (installed: {VERSION}). '
            'Upgrade logfire with your package manager.\n'
        )
