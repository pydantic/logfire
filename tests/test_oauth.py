"""Tests for the OAuth 2.1 device flow (`logfire auth --oauth`).

Covers:
- Metadata discovery + PKCE + device-code polling.
- DCR fallback when `logfire-cli` is rejected with `invalid_client`.
- Keyring-backed storage and file-only fallback.
- Transparent refresh with file locking.
- End-to-end `main(['auth', '--oauth'])` via requests_mock.
"""

from __future__ import annotations

import threading
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import requests
import requests_mock

from logfire._internal import oauth, token_storage
from logfire._internal.auth import UserTokenCollection
from logfire._internal.cli import main
from logfire._internal.client import LogfireClient
from logfire._internal.token_storage import KEYRING_SERVICE, StoredOAuthSecrets, TokenStorage, file_lock


def _noop(*_a: Any, **_k: Any) -> Any:
    return ''


BASE_URL = 'https://logfire-us.pydantic.dev'
METADATA_URL = f'{BASE_URL}/.well-known/oauth-authorization-server'
DEVICE_URL = f'{BASE_URL}/oauth2/device'
TOKEN_URL = f'{BASE_URL}/oauth2/token'
REGISTER_URL = f'{BASE_URL}/oauth2/register'


def _metadata() -> dict[str, Any]:
    return {
        'issuer': BASE_URL,
        'authorization_endpoint': f'{BASE_URL}/oauth2/authorize',
        'token_endpoint': TOKEN_URL,
        'device_authorization_endpoint': DEVICE_URL,
        'registration_endpoint': REGISTER_URL,
        'code_challenge_methods_supported': ['S256'],
        'grant_types_supported': [
            'urn:ietf:params:oauth:grant-type:device_code',
            'refresh_token',
        ],
        'scopes_supported': ['project:read_dashboard'],
    }


def _device_response() -> dict[str, Any]:
    return {
        'device_code': 'DEVICE_CODE_42',
        'user_code': 'USER-CODE',
        'verification_uri': 'https://example.com/device',
        'verification_uri_complete': 'https://example.com/device?user_code=USER-CODE',
        'expires_in': 300,
        'interval': 0,
    }


class _InMemoryKeyring:
    """Minimal keyring backend used to exercise the keyring-backed code paths."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.store[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _InMemoryKeyring:
    fake = _InMemoryKeyring()
    monkeypatch.setattr(token_storage, '_keyring_import_ok', True)
    monkeypatch.setattr(token_storage, '_keyring_module', fake)
    return fake


@pytest.fixture
def no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_storage, '_keyring_import_ok', False)
    monkeypatch.setattr(token_storage, '_keyring_module', None)


def test_pkce_pair_shape() -> None:
    verifier, challenge = oauth.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert '=' not in verifier
    assert '=' not in challenge
    # challenge is deterministic from the verifier.
    _, challenge2 = oauth.generate_pkce_pair()
    assert challenge != challenge2  # different verifiers -> different challenges


def test_run_device_flow_preregistered(fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(DEVICE_URL, json=_device_response())
        m.post(
            TOKEN_URL,
            [
                {'json': {'detail': {'error': 'authorization_pending'}}, 'status_code': 400},
                {
                    'json': {
                        'access_token': 'AT',
                        'refresh_token': 'RT',
                        'token_type': 'Bearer',
                        'expires_in': 3600,
                        'scope': 'project:read_dashboard',
                    }
                },
            ],
        )
        with requests.Session() as session:
            result = oauth.run_device_flow(session, BASE_URL)
    assert result.client_id == 'logfire-cli'
    assert result.token.get('access_token') == 'AT'
    assert result.token.get('refresh_token') == 'RT'


def test_run_device_flow_falls_back_to_dcr(fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)

    call_log: list[dict[str, Any]] = []

    def device_callback(request: Any, context: Any) -> Any:
        form = dict(x.split('=', 1) for x in request.text.split('&'))
        call_log.append(form)
        if form['client_id'] == 'logfire-cli':
            context.status_code = 401
            return {'error': 'invalid_client'}
        context.status_code = 200
        return _device_response()

    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(DEVICE_URL, json=device_callback)
        m.post(REGISTER_URL, json={'client_id': 'dcr-issued-123'})
        m.post(
            TOKEN_URL,
            json={
                'access_token': 'AT',
                'refresh_token': 'RT',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'scope': 'project:read_dashboard',
            },
        )
        with requests.Session() as session:
            result = oauth.run_device_flow(session, BASE_URL)
    assert result.client_id == 'dcr-issued-123'
    assert [entry['client_id'] for entry in call_log] == ['logfire-cli', 'dcr-issued-123']


def test_run_device_flow_no_dcr_endpoint_errors(
    fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    from logfire.exceptions import LogfireConfigError

    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)

    metadata = _metadata()
    metadata.pop('registration_endpoint')

    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=metadata)
        m.post(DEVICE_URL, status_code=401, json={'error': 'invalid_client'})
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='does not expose a Dynamic Client Registration'):
                oauth.run_device_flow(session, BASE_URL)


def test_token_storage_keyring_roundtrip(fake_keyring: _InMemoryKeyring) -> None:
    storage = TokenStorage()
    assert storage.keyring_available is True
    assert storage.save('https://logfire-us.pydantic.dev', StoredOAuthSecrets('ACCESS', 'REFRESH')) is True
    loaded = storage.load('https://logfire-us.pydantic.dev')
    assert loaded is not None
    assert loaded.access_token == 'ACCESS'
    assert loaded.refresh_token == 'REFRESH'
    storage.delete('https://logfire-us.pydantic.dev')
    assert storage.load('https://logfire-us.pydantic.dev') is None


def test_token_storage_without_keyring(no_keyring: None) -> None:
    storage = TokenStorage()
    assert storage.keyring_available is False
    assert storage.save('https://logfire-us.pydantic.dev', StoredOAuthSecrets('A', 'B')) is False
    assert storage.load('https://logfire-us.pydantic.dev') is None


def test_user_token_collection_keyring_record(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    # Secrets in keyring, metadata in TOML (no inline tokens).
    written = auth_file.read_text()
    assert 'auth_method = "oauth"' in written
    assert 'keyring_service = "logfire-oauth"' in written
    assert 'AT' not in written and 'RT' not in written
    # Round trip through a fresh collection.
    reloaded = UserTokenCollection(path=auth_file)
    token = reloaded.get_token(BASE_URL)
    assert token.token == 'AT'
    assert token.refresh_token == 'RT'
    assert token.header_value == 'Bearer AT'
    assert token.auth_method == 'oauth'


def test_user_token_collection_file_only(tmp_path: Path, no_keyring: None) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='dcr-issued-123',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    written = auth_file.read_text()
    assert 'keyring_service' not in written
    assert 'oauth_token = "AT"' in written
    assert 'refresh_token = "RT"' in written
    # File mode 0600 when we persist secrets inline.
    mode = auth_file.stat().st_mode & 0o777
    assert mode == 0o600
    reloaded = UserTokenCollection(path=auth_file)
    token = reloaded.get_token(BASE_URL)
    assert token.token == 'AT'
    assert token.client_id == 'dcr-issued-123'


def test_logout_clears_keyring(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    assert fake_keyring.store
    collection.logout(BASE_URL)
    assert not fake_keyring.store
    assert auth_file.read_text() == ''


def test_refresh_triggers_when_near_expiry(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    # Token expires in 5 seconds -> inside the 60s refresh margin.
    expiration = (datetime.now(tz=timezone.utc) + timedelta(seconds=5)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='OLD_REFRESH',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    token = collection.get_token(BASE_URL)
    assert token.needs_refresh
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(
            TOKEN_URL,
            json={
                'access_token': 'NEW',
                'refresh_token': 'NEW_REFRESH',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'scope': 'project:read_dashboard',
            },
        )
        with requests.Session() as session:
            refreshed = collection.refresh_if_needed(token, session)
    assert refreshed.token == 'NEW'
    assert refreshed.refresh_token == 'NEW_REFRESH'
    # On-disk record should reflect the new expiration.
    reloaded = UserTokenCollection(path=auth_file)
    current = reloaded.get_token(BASE_URL)
    assert current.token == 'NEW'
    assert not current.needs_refresh


def test_refresh_reuses_result_from_concurrent_process(
    tmp_path: Path, fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(seconds=5)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='OLD_REFRESH',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    stale = collection.get_token(BASE_URL)
    # Simulate another process finishing its refresh before we get the lock:
    # when `refresh_if_needed` reloads the file it should see fresh tokens and
    # skip the network call entirely.
    other = UserTokenCollection(path=auth_file)
    fresh_expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    other.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='NEW',
        refresh_token='NEW_REFRESH',
        scope='project:read_dashboard',
        expiration=fresh_expiration,
    )
    # If we *do* hit the network, the test fails immediately because no mocks are registered.
    with requests.Session() as session:
        result = collection.refresh_if_needed(stale, session)
    assert result.token == 'NEW'
    assert stale.token == 'NEW'  # caller's reference updated in place
    assert stale.refresh_token == 'NEW_REFRESH'


def test_file_lock_serializes_writers(tmp_path: Path) -> None:
    path = tmp_path / 'default.toml'
    path.touch()
    observed: list[int] = []
    barrier = threading.Barrier(2)

    def worker(tag: int, hold_for: float) -> None:
        barrier.wait()
        with file_lock(path):
            observed.append(tag)
            # Hold the lock long enough that a competing acquirer must wait.
            import time as _t

            _t.sleep(hold_for)
            observed.append(-tag)

    t1 = threading.Thread(target=worker, args=(1, 0.1))
    t2 = threading.Thread(target=worker, args=(2, 0.1))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # Each critical section must complete before the other begins.
    pairs = [(observed[i], observed[i + 1]) for i in range(0, len(observed), 2)]
    for entry, exit_ in pairs:
        assert entry == -exit_


def test_cli_main_oauth_flow(
    tmp_path: Path, fake_keyring: _InMemoryKeyring, capsys: pytest.CaptureFixture[str]
) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('builtins.input', _noop))
        stack.enter_context(patch('webbrowser.open', _noop))
        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(METADATA_URL, json=_metadata())
        m.post(DEVICE_URL, json=_device_response())
        m.post(
            TOKEN_URL,
            json={
                'access_token': 'AT',
                'refresh_token': 'RT',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'scope': 'project:read_dashboard',
            },
        )
        main(['--region', 'us', 'auth', '--oauth'])
    written = auth_file.read_text()
    assert 'auth_method = "oauth"' in written
    assert 'client_id = "logfire-cli"' in written
    err = capsys.readouterr().err
    assert 'Successfully authenticated with OAuth 2.1!' in err
    assert KEYRING_SERVICE in err


def test_logfire_client_uses_bearer_for_oauth(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    user_token = collection.get_token(BASE_URL)
    client = LogfireClient(user_token=user_token, collection=collection)
    assert client._session.headers['Authorization'] == 'Bearer AT'  # pyright: ignore[reportPrivateUsage]


def test_logfire_client_refreshes_expired_oauth_token(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    # Expired access token — construction must refresh rather than raise.
    expired = (datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expired,
    )
    user_token = collection.user_tokens[BASE_URL]
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(
            TOKEN_URL,
            json={
                'access_token': 'NEW',
                'refresh_token': 'RT',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'scope': 'project:read_dashboard',
            },
        )
        client = LogfireClient(user_token=user_token, collection=collection)
    assert client._session.headers['Authorization'] == 'Bearer NEW'  # pyright: ignore[reportPrivateUsage]


def test_is_logged_in_with_refreshable_oauth(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    # Expired but refreshable => still considered "logged in".
    expired = (datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expired,
    )
    assert collection.is_logged_in(BASE_URL) is True


def test_get_token_does_not_reject_expired_oauth(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expired = (datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expired,
    )
    # Unlike legacy tokens, expired OAuth tokens are returned — the caller
    # (LogfireClient) is responsible for refreshing them.
    token = collection.get_token(BASE_URL)
    assert token.token == 'OLD'
    assert token.is_expired is True


def test_poll_for_token_handles_slow_down(fake_keyring: _InMemoryKeyring) -> None:
    sleeps: list[float] = []

    def fake_sleep(n: float) -> None:
        sleeps.append(n)

    metadata: oauth.OAuthServerMetadata = {'token_endpoint': TOKEN_URL}
    with requests_mock.Mocker() as m:
        m.post(
            TOKEN_URL,
            [
                {'json': {'error': 'slow_down'}, 'status_code': 400},
                {'json': {'error': 'authorization_pending'}, 'status_code': 400},
                {
                    'json': {
                        'access_token': 'AT',
                        'refresh_token': 'RT',
                        'token_type': 'Bearer',
                        'expires_in': 3600,
                        'scope': 'project:read_dashboard',
                    }
                },
            ],
        )
        with requests.Session() as session:
            response = oauth.poll_for_token(
                session,
                metadata,
                device_code='DC',
                client_id='logfire-cli',
                code_verifier='v',
                interval=1,
                expires_in=300,
                sleep=fake_sleep,
            )
    assert response is not None
    assert response.get('access_token') == 'AT'
    # After one slow_down the interval should grow by 5 seconds.
    assert sleeps == [1, 6, 6]
