from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from ...exceptions import LogfireConfigError
from ..auth import DEFAULT_FILE, UserTokenCollection, poll_for_token, request_device_code
from ..config import REGIONS
from ..oauth import DEFAULT_SCOPE, run_device_flow
from ..token_storage import KEYRING_SERVICE


def _prompt_region(logfire_url: str | None) -> str:
    if logfire_url:
        return logfire_url
    selected_region = -1
    while not (1 <= selected_region <= len(REGIONS)):
        sys.stderr.write('Logfire is available in multiple data regions. Please select one:\n')
        for i, (region_id, region_data) in enumerate(REGIONS.items(), start=1):
            sys.stderr.write(f'{i}. {region_id.upper()} (GCP region: {region_data["gcp_region"]})\n')
        try:
            selected_region = int(input(f'Selected region [{"/".join(str(i) for i in range(1, len(REGIONS) + 1))}]: '))
        except ValueError:
            selected_region = -1
    return list(REGIONS.values())[selected_region - 1]['base_url']


def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This will authenticate your machine with Logfire and store the credentials.
    """
    logfire_url: str | None = args.logfire_url

    tokens_collection = UserTokenCollection()
    logged_in = tokens_collection.is_logged_in(logfire_url)

    if logged_in:
        sys.stderr.writelines(
            (
                f'You are already logged in. (Your credentials are stored in {DEFAULT_FILE})\n',
                'If you would like to log in using a different account, use the --region argument:\n',
                'logfire --region <region> auth\n',
            )
        )
        return

    sys.stderr.writelines(
        (
            '\n',
            'Welcome to Logfire! 🔥\n',
            'Before you can send data to Logfire, we need to authenticate you.\n',
            '\n',
        )
    )
    logfire_url = _prompt_region(logfire_url)

    if getattr(args, 'oauth', False):
        _run_oauth_flow(args, tokens_collection, logfire_url)
        return

    _run_legacy_flow(args, tokens_collection, logfire_url)


def _run_legacy_flow(args: argparse.Namespace, tokens_collection: UserTokenCollection, logfire_url: str) -> None:
    device_code, frontend_auth_url = request_device_code(args._session, logfire_url)
    frontend_host = urlparse(frontend_auth_url).netloc

    # We are not using the `prompt` parameter from `input` here because we want to write to stderr.
    sys.stderr.write(f'Press Enter to open {frontend_host} in your browser...\n')
    input()

    try:
        webbrowser.open(frontend_auth_url, new=2)
    except webbrowser.Error:
        pass
    sys.stderr.writelines(
        (
            f"Please open {frontend_auth_url} in your browser to authenticate if it hasn't already.\n",
            'Waiting for you to authenticate with Logfire...\n',
        )
    )

    tokens_collection.add_token(logfire_url, poll_for_token(args._session, device_code, logfire_url))
    sys.stderr.write('Successfully authenticated!\n')
    sys.stderr.write(f'\nYour Logfire credentials are stored in {DEFAULT_FILE}\n')


def _run_oauth_flow(args: argparse.Namespace, tokens_collection: UserTokenCollection, logfire_url: str) -> None:
    # Reuse any previously DCR-issued client id for this base URL so we don't
    # re-register on every login.
    cached = tokens_collection.user_tokens.get(logfire_url)
    cached_client_id = cached.client_id if cached and cached.auth_method == 'oauth' else None

    result = run_device_flow(
        args._session,
        logfire_url,
        cached_client_id=cached_client_id,
        scope=DEFAULT_SCOPE,
    )
    token = result.token
    expiration = (datetime.now(tz=timezone.utc) + timedelta(seconds=int(token.get('expires_in', 3600)))).isoformat()
    added = tokens_collection.add_oauth_token(
        logfire_url,
        client_id=result.client_id,
        access_token=token.get('access_token', ''),
        refresh_token=token.get('refresh_token', ''),
        scope=token.get('scope', '') or DEFAULT_SCOPE,
        expiration=expiration,
    )
    sys.stderr.write('Successfully authenticated with OAuth 2.1!\n')
    if added.keyring_service:
        sys.stderr.write(
            f'Access/refresh tokens stored in the system keyring (service: {KEYRING_SERVICE}).\n'
            f'Metadata stored in {DEFAULT_FILE}.\n'
        )
    else:
        sys.stderr.write(
            'The system keyring is not available; tokens were stored in '
            f'{DEFAULT_FILE} with permissions 0600. Install `logfire[cli]` '
            'to keep them in the OS keyring instead.\n'
        )


def parse_logout(args: argparse.Namespace) -> None:
    """Log out from Logfire."""
    logfire_url: str | None = args.logfire_url

    tokens_collection = UserTokenCollection()

    try:
        removed = tokens_collection.logout(logfire_url)
    except LogfireConfigError as e:
        sys.stderr.write(f'{e}\n')
        sys.exit(1)

    for url in removed:
        sys.stderr.write(f'Successfully logged out from {url}\n')
    sys.stderr.write(f'\nYour Logfire credentials have been removed from {DEFAULT_FILE}\n')
