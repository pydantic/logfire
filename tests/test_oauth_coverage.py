"""Exhaustive coverage for the OAuth 2.1 device-flow stack.

Fills every reachable branch in:
    logfire/_internal/auth.py
    logfire/_internal/oauth.py
    logfire/_internal/token_storage.py
    logfire/_internal/cli/auth.py
    logfire/_internal/client.py   (only the new/changed code paths)

These tests are kept separate from `test_oauth.py` (which exercises the
happy-path scenarios) to keep that file focused while still making sure we
cover every error branch, early-return, and edge case.
"""

from __future__ import annotations

import threading
import webbrowser
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
import requests
import requests_mock

from logfire._internal import oauth, token_storage
from logfire._internal.auth import DEFAULT_OAUTH_CLIENT_ID, UserToken, UserTokenCollection
from logfire._internal.cli import main
from logfire._internal.cli.auth import _prompt_region  # pyright: ignore[reportPrivateUsage]
from logfire._internal.client import LogfireClient
from logfire._internal.token_storage import (
    KEYRING_SERVICE,
    SecretStr,
    StoredOAuthSecrets,
    TokenStorage,
    file_lock,
)
from logfire.exceptions import LogfireConfigError


def _no_sleep(_seconds: float) -> None:
    """Typed replacement for `lambda _n: None` (pyright dislikes untyped lambdas)."""


BASE_URL = 'https://logfire-us.pydantic.dev'
METADATA_URL = f'{BASE_URL}/.well-known/oauth-authorization-server'
DEVICE_URL = f'{BASE_URL}/oauth2/device'
TOKEN_URL = f'{BASE_URL}/oauth2/token'
REGISTER_URL = f'{BASE_URL}/oauth2/register'


def _noop(*_a: Any, **_k: Any) -> Any:
    return ''


def _metadata(**overrides: Any) -> oauth.OAuthServerMetadata:
    base: dict[str, Any] = {
        'issuer': BASE_URL,
        'authorization_endpoint': f'{BASE_URL}/oauth2/authorize',
        'token_endpoint': TOKEN_URL,
        'device_authorization_endpoint': DEVICE_URL,
        'registration_endpoint': REGISTER_URL,
    }
    base.update(overrides)
    return cast(oauth.OAuthServerMetadata, base)


class _InMemoryKeyring:
    def __init__(self, probe_error: Exception | None = None) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self._probe_error = probe_error
        self.set_errors: list[Exception] = []
        self.delete_errors: list[Exception] = []

    def get_password(self, service: str, username: str) -> str | None:
        if self._probe_error is not None and username == '__logfire_probe__':
            error = self._probe_error
            self._probe_error = None
            raise error
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        if self.set_errors:
            raise self.set_errors.pop(0)
        self.store[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        if self.delete_errors:
            raise self.delete_errors.pop(0)
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


# ---------------------------------------------------------------------------
# SecretStr
# ---------------------------------------------------------------------------


def test_secretstr_obscures_value() -> None:
    s = SecretStr('hunter2')
    assert s.get_secret_value() == 'hunter2'
    assert str(s) == '**********'
    assert 'hunter2' not in repr(s)
    assert bool(s) is True
    assert hash(s) == hash('hunter2')
    assert s == SecretStr('hunter2')
    assert s != SecretStr('other')
    # Comparison with non-SecretStr returns NotImplemented → False to the caller.
    assert (s == 'hunter2') is False


def test_secretstr_empty_is_falsy() -> None:
    s = SecretStr('')
    assert bool(s) is False
    assert str(s) == ''


# ---------------------------------------------------------------------------
# oauth.py — error / edge branches
# ---------------------------------------------------------------------------


def test_discover_metadata_network_failure() -> None:
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, exc=requests.exceptions.ConnectionError)
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='Failed to fetch OAuth server metadata'):
                oauth.discover_metadata(session, BASE_URL)


def test_register_client_without_registration_endpoint() -> None:
    with requests.Session() as session:
        with pytest.raises(LogfireConfigError, match='does not expose a Dynamic Client Registration'):
            oauth.register_client(session, cast(oauth.OAuthServerMetadata, {'issuer': BASE_URL}))


def test_register_client_network_failure() -> None:
    with requests_mock.Mocker() as m:
        m.post(REGISTER_URL, exc=requests.exceptions.ConnectionError)
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='Failed to register an OAuth client'):
                oauth.register_client(session, _metadata())


def test_register_client_missing_client_id() -> None:
    with requests_mock.Mocker() as m:
        m.post(REGISTER_URL, json={})  # 200 OK but no client_id
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='did not include a `client_id`'):
                oauth.register_client(session, _metadata())


def test_unregister_client_swallows_request_error() -> None:
    with requests_mock.Mocker() as m:
        m.delete(f'{BASE_URL}/oauth2/register/abc', exc=requests.exceptions.ConnectionError)
        with requests.Session() as session:
            # Must not raise — best-effort.
            oauth.unregister_client(
                session,
                registration_client_uri=f'{BASE_URL}/oauth2/register/abc',
                registration_access_token='RAT',
            )


def test_error_code_handles_non_json_and_non_dict() -> None:
    # Craft a response whose body is raw text (no JSON).
    with requests_mock.Mocker() as m:
        m.get(f'{BASE_URL}/plain', text='not json')
        m.get(f'{BASE_URL}/list', json=['a', 'b'])  # valid JSON but not a dict
        # `detail` is present but its `error` value is not a string.
        m.get(f'{BASE_URL}/detail-no-error', json={'detail': {'unrelated': 1}})
        with requests.Session() as session:
            r1 = session.get(f'{BASE_URL}/plain')
            r2 = session.get(f'{BASE_URL}/list')
            r3 = session.get(f'{BASE_URL}/detail-no-error')
    error_code = oauth._error_code  # pyright: ignore[reportPrivateUsage]
    assert error_code(r1) == ''
    assert error_code(r2) == ''
    assert error_code(r3) == ''


def test_request_device_authorization_missing_endpoint() -> None:
    with requests.Session() as session:
        with pytest.raises(LogfireConfigError, match='does not declare a `device_authorization_endpoint`'):
            oauth.request_device_authorization(
                session,
                cast(oauth.OAuthServerMetadata, {'issuer': BASE_URL}),
                client_id='logfire-cli',
                code_challenge='ch',
                scope=None,
            )


def test_request_device_authorization_unexpected_error() -> None:
    with requests_mock.Mocker() as m:
        m.post(DEVICE_URL, status_code=500, text='boom')
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='Failed to request OAuth device authorization'):
                oauth.request_device_authorization(
                    session,
                    _metadata(),
                    client_id='logfire-cli',
                    code_challenge='ch',
                    scope=None,
                )


def test_poll_for_token_missing_endpoint() -> None:
    with requests.Session() as session:
        with pytest.raises(LogfireConfigError, match='does not declare a `token_endpoint`'):
            oauth.poll_for_token(
                session,
                cast(oauth.OAuthServerMetadata, {'issuer': BASE_URL}),
                device_code='DC',
                client_id='logfire-cli',
                code_verifier='v',
                interval=1,
                expires_in=10,
                sleep=_no_sleep,
            )


def test_poll_for_token_access_denied(capsys: pytest.CaptureFixture[str]) -> None:
    metadata: oauth.OAuthServerMetadata = {'token_endpoint': TOKEN_URL}
    with requests_mock.Mocker() as m:
        m.post(TOKEN_URL, json={'error': 'access_denied'}, status_code=400)
        with requests.Session() as session:
            result = oauth.poll_for_token(
                session,
                metadata,
                device_code='DC',
                client_id='logfire-cli',
                code_verifier='v',
                interval=1,
                expires_in=10,
                sleep=_no_sleep,
            )
    assert result is None
    assert 'denied by the user' in capsys.readouterr().err


def test_poll_for_token_expired(capsys: pytest.CaptureFixture[str]) -> None:
    metadata: oauth.OAuthServerMetadata = {'token_endpoint': TOKEN_URL}
    with requests_mock.Mocker() as m:
        m.post(TOKEN_URL, json={'error': 'expired_token'}, status_code=400)
        with requests.Session() as session:
            result = oauth.poll_for_token(
                session,
                metadata,
                device_code='DC',
                client_id='logfire-cli',
                code_verifier='v',
                interval=1,
                expires_in=10,
                sleep=_no_sleep,
            )
    assert result is None
    assert 'device code expired' in capsys.readouterr().err


def test_poll_for_token_unknown_error_is_fatal() -> None:
    metadata: oauth.OAuthServerMetadata = {'token_endpoint': TOKEN_URL}
    with requests_mock.Mocker() as m:
        m.post(TOKEN_URL, json={'error': 'temporarily_unavailable'}, status_code=503)
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='temporarily_unavailable'):
                oauth.poll_for_token(
                    session,
                    metadata,
                    device_code='DC',
                    client_id='logfire-cli',
                    code_verifier='v',
                    interval=1,
                    expires_in=10,
                    sleep=_no_sleep,
                )


def test_poll_for_token_times_out(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    metadata: oauth.OAuthServerMetadata = {'token_endpoint': TOKEN_URL}
    # Make `time.monotonic` jump past the deadline on the second call so the
    # loop exits without ever seeing a success response.
    clock_values = iter([0.0, 999.0, 999.0])
    monkeypatch.setattr(oauth.time, 'monotonic', lambda: next(clock_values))
    with requests_mock.Mocker() as m:
        m.post(TOKEN_URL, json={'error': 'authorization_pending'}, status_code=400)
        with requests.Session() as session:
            result = oauth.poll_for_token(
                session,
                metadata,
                device_code='DC',
                client_id='logfire-cli',
                code_verifier='v',
                interval=1,
                expires_in=10,
                sleep=_no_sleep,
            )
    assert result is None
    assert 'Timed out' in capsys.readouterr().err


def test_refresh_access_token_missing_endpoint() -> None:
    with requests.Session() as session:
        with pytest.raises(LogfireConfigError, match='does not declare a `token_endpoint`'):
            oauth.refresh_access_token(
                session, cast(oauth.OAuthServerMetadata, {'issuer': BASE_URL}), refresh_token='RT', client_id='c'
            )


def test_refresh_access_token_unexpected_error() -> None:
    with requests_mock.Mocker() as m:
        m.post(TOKEN_URL, status_code=500, text='boom')
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='Failed to refresh the OAuth access token'):
                oauth.refresh_access_token(session, _metadata(), refresh_token='RT', client_id='c')


def test_run_device_flow_rejected_after_dcr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(DEVICE_URL, status_code=401, json={'error': 'invalid_client'})
        m.post(REGISTER_URL, json={'client_id': 'dcr-id'})
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='rejected even after dynamic client registration'):
                oauth.run_device_flow(session, BASE_URL)


def test_run_device_flow_tolerates_eof_and_webbrowser_error(
    fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_eof(*_a: Any, **_k: Any) -> str:
        raise EOFError

    def _raise_browser(*_a: Any, **_k: Any) -> bool:
        raise webbrowser.Error('no display')

    monkeypatch.setattr('builtins.input', _raise_eof)
    monkeypatch.setattr('webbrowser.open', _raise_browser)
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(
            DEVICE_URL,
            json={
                'device_code': 'DC',
                'user_code': 'UC',
                'verification_uri': 'http://x/',
                'interval': 0,
                'expires_in': 30,
            },
        )
        m.post(
            TOKEN_URL,
            json={
                'access_token': 'AT',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'scope': 'project:read_dashboard',
            },
        )
        with requests.Session() as session:
            with pytest.warns(UserWarning, match='did not return a refresh_token'):
                result = oauth.run_device_flow(session, BASE_URL)
    assert result.client_id == DEFAULT_OAUTH_CLIENT_ID


def test_run_device_flow_raises_when_polling_declines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(
            DEVICE_URL,
            json={
                'device_code': 'DC',
                'user_code': 'UC',
                'verification_uri': 'http://x/',
                'interval': 0,
                'expires_in': 30,
            },
        )
        m.post(TOKEN_URL, json={'error': 'access_denied'}, status_code=400)
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='did not complete'):
                oauth.run_device_flow(session, BASE_URL)


# ---------------------------------------------------------------------------
# token_storage.py — error / edge branches
# ---------------------------------------------------------------------------


class _FakeKeyringError(Exception):
    pass


def test_keyring_unavailable_when_probe_raises_keyring_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _InMemoryKeyring(probe_error=_FakeKeyringError('no backend'))
    monkeypatch.setattr(token_storage, '_keyring_import_ok', True)
    monkeypatch.setattr(token_storage, '_keyring_module', fake)
    monkeypatch.setattr(token_storage, '_keyring_error', _FakeKeyringError)
    storage = TokenStorage()
    assert storage.keyring_available is False


def test_keyring_unavailable_when_probe_raises_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _InMemoryKeyring(probe_error=RuntimeError('weird'))
    monkeypatch.setattr(token_storage, '_keyring_import_ok', True)
    monkeypatch.setattr(token_storage, '_keyring_module', fake)
    storage = TokenStorage()
    assert storage.keyring_available is False


def test_save_reports_keyring_error_and_falls_back(
    fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(token_storage, '_keyring_error', _FakeKeyringError)
    fake_keyring.set_errors.append(_FakeKeyringError('disk full'))
    storage = TokenStorage()
    assert storage.save('u', StoredOAuthSecrets('A', 'R')) is False
    assert 'disk full' in capsys.readouterr().err


def test_save_returns_false_without_keyring(no_keyring: None) -> None:
    storage = TokenStorage()
    assert storage.save('u', StoredOAuthSecrets('A', 'R')) is False


def test_load_returns_none_on_keyring_error(fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_storage, '_keyring_error', _FakeKeyringError)
    storage = TokenStorage()
    # Prime keyring_available, then make every subsequent `get_password` raise.
    assert storage.keyring_available is True

    def _boom(*_a: Any, **_k: Any) -> None:
        raise _FakeKeyringError('locked')

    monkeypatch.setattr(fake_keyring, 'get_password', _boom)
    assert storage.load('u') is None


def test_load_returns_none_on_invalid_json(fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_storage, '_keyring_error', _FakeKeyringError)
    storage = TokenStorage()
    assert storage.keyring_available is True
    fake_keyring.store[(KEYRING_SERVICE, 'u')] = 'not-json'
    assert storage.load('u') is None


def test_load_returns_none_when_fields_missing(fake_keyring: _InMemoryKeyring) -> None:
    storage = TokenStorage()
    assert storage.keyring_available is True
    import json

    fake_keyring.store[(KEYRING_SERVICE, 'u')] = json.dumps({'access_token': 'A'})  # no refresh_token
    assert storage.load('u') is None


def test_load_returns_none_when_empty(fake_keyring: _InMemoryKeyring) -> None:
    storage = TokenStorage()
    # No entry in the keyring.
    assert storage.load('missing') is None


def test_delete_ignored_when_keyring_unavailable(no_keyring: None) -> None:
    storage = TokenStorage()
    storage.delete('u')  # should not raise


def test_delete_swallows_keyring_errors(fake_keyring: _InMemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_storage, '_keyring_error', _FakeKeyringError)
    storage = TokenStorage()
    assert storage.keyring_available is True
    fake_keyring.delete_errors.append(_FakeKeyringError('locked'))
    # Must not raise even though delete_password would.
    storage.delete('u')


# ---------------------------------------------------------------------------
# auth.py — error / edge branches
# ---------------------------------------------------------------------------


def test_from_oauth_record_returns_none_when_keyring_dropped(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    # Persist an OAuth record via the collection, then wipe the keyring blob.
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
    fake_keyring.store.clear()
    # A fresh collection sees the TOML record but can't rehydrate secrets.
    reloaded = UserTokenCollection(path=auth_file)
    assert reloaded.user_tokens == {}


def test_usertoken_str_oauth_and_header_value_legacy() -> None:
    oauth_token = UserToken(
        token=SecretStr('abcdef'),
        base_url=BASE_URL,
        expiration='2099-12-31',
        refresh_token=SecretStr('rt'),
    )
    assert str(oauth_token) == f'OAuth ({BASE_URL}) - abcde****'
    # User tokens send the raw value without a `Bearer` prefix.
    user_token = UserToken(token=SecretStr('pylf_xxx'), base_url=BASE_URL, expiration='2099-12-31')
    assert user_token.auth_method == 'user_token'
    assert user_token.header_value == 'pylf_xxx'
    # `needs_refresh` is meaningless for user tokens.
    assert user_token.needs_refresh is False


def test_refresh_if_needed_short_circuits_for_legacy_and_fresh(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    legacy = UserToken(token=SecretStr('pylf_xxx'), base_url=BASE_URL, expiration='2099-12-31')
    # Legacy tokens never hit the network.
    with requests.Session() as session:
        assert collection.refresh_if_needed(legacy, session) is legacy

    # Fresh OAuth token (far-future expiration) is likewise not refreshed.
    fresh = UserToken(
        token=SecretStr('AT'),
        base_url=BASE_URL,
        expiration='2099-12-31',
        refresh_token=SecretStr('RT'),
    )
    with requests.Session() as session:
        assert collection.refresh_if_needed(fresh, session) is fresh


def test_refresh_if_needed_raises_when_server_omits_access_token(
    tmp_path: Path, fake_keyring: _InMemoryKeyring
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
    token = collection.get_token(BASE_URL)
    assert token.needs_refresh
    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(TOKEN_URL, json={'token_type': 'Bearer', 'expires_in': 3600})  # no access_token
        with requests.Session() as session:
            with pytest.raises(LogfireConfigError, match='did not include an access_token'):
                collection.refresh_if_needed(token, session)


def test_is_logged_in_without_base_url(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    assert collection.is_logged_in() is False
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    # True because at least one token (any URL) is usable.
    assert collection.is_logged_in() is True


# ---------------------------------------------------------------------------
# cli/auth.py — region prompt, logout, no-keyring messaging
# ---------------------------------------------------------------------------


def test_prompt_region_retries_until_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(['', 'not-a-number', '9', '1'])
    monkeypatch.setattr('builtins.input', lambda _p='': next(responses))
    url = _prompt_region(None)
    assert url.startswith('https://')


def test_prompt_region_passthrough_when_url_provided() -> None:
    assert _prompt_region('https://explicit.example') == 'https://explicit.example'


def test_cli_oauth_flow_without_keyring_uses_file(
    tmp_path: Path, no_keyring: None, capsys: pytest.CaptureFixture[str]
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
        m.post(
            DEVICE_URL,
            json={
                'device_code': 'DC',
                'user_code': 'UC',
                'verification_uri': 'http://x/',
                'interval': 0,
                'expires_in': 30,
            },
        )
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
    # Tokens are inline because keyring is unavailable.
    written = auth_file.read_text()
    assert 'oauth_token = "AT"' in written
    assert 'refresh_token = "RT"' in written
    err = capsys.readouterr().err
    assert 'keyring is not available' in err
    assert 'logfire[cli]' in err


def test_cli_logout_success(tmp_path: Path, fake_keyring: _InMemoryKeyring, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / 'default.toml'
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        # Seed the collection.
        UserTokenCollection(path=auth_file).add_oauth_token(
            BASE_URL,
            client_id='logfire-cli',
            access_token='AT',
            refresh_token='RT',
            scope='project:read_dashboard',
            expiration=expiration,
        )
        main(['--region', 'us', 'auth', 'logout'])
    err = capsys.readouterr().err
    assert 'Successfully logged out from https://logfire-us.pydantic.dev' in err
    assert auth_file.read_text() == ''


def test_cli_logout_when_not_logged_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.touch()
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        with pytest.raises(SystemExit) as excinfo:
            main(['auth', 'logout'])
    assert excinfo.value.code == 1
    assert 'not logged into Logfire' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# client.py — new/changed behaviors
# ---------------------------------------------------------------------------


def test_logfire_client_legacy_header_has_no_bearer_prefix(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-us.pydantic.dev"]\ntoken = "pylf_v1_us_abc"\nexpiration = "2099-12-31T23:59:59"\n'
    )
    collection = UserTokenCollection(path=auth_file)
    token = collection.get_token(BASE_URL)
    client = LogfireClient(user_token=token, collection=collection)
    assert client._session.headers['Authorization'] == 'pylf_v1_us_abc'  # pyright: ignore[reportPrivateUsage]
    # Read-back via the legacy accessor uses .get_secret_value() under the hood.
    assert client._token == 'pylf_v1_us_abc'  # pyright: ignore[reportPrivateUsage]


def test_logfire_client_rejects_expired_token_without_refresh(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-us.pydantic.dev"]\ntoken = "pylf_v1_us_abc"\nexpiration = "1970-01-01T00:00:00"\n'
    )
    collection = UserTokenCollection(path=auth_file)
    user_token = collection.user_tokens[BASE_URL]
    with pytest.raises(RuntimeError, match='expired'):
        LogfireClient(user_token=user_token, collection=collection)


def test_logfire_client_from_url_single_legacy_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-us.pydantic.dev"]\ntoken = "pylf_v1_us_abc"\nexpiration = "2099-12-31T23:59:59"\n'
    )
    monkeypatch.setattr('logfire._internal.auth.DEFAULT_FILE', auth_file)
    client = LogfireClient.from_url(BASE_URL)
    assert client.base_url == BASE_URL


def test_logfire_client_401_triggers_refresh_and_retry(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    # Valid, not-yet-expiring token so _get_raw won't proactively refresh.
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    user_token = collection.get_token(BASE_URL)
    client = LogfireClient(user_token=user_token, collection=collection)

    seen_headers: list[str] = []

    def _status(request: Any, context: Any) -> Any:
        seen_headers.append(str(request.headers.get('Authorization')))
        if len(seen_headers) == 1:
            context.status_code = 401
            return {}
        context.status_code = 200
        return {'ok': True}

    with requests_mock.Mocker() as m:
        m.get(f'{BASE_URL}/v1/test', json=_status)
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
        response = client._get_raw('/v1/test')  # pyright: ignore[reportPrivateUsage]
    assert response.json() == {'ok': True}
    # First request used OLD (pre-401), retry used NEW after forced refresh.
    assert seen_headers == ['Bearer OLD', 'Bearer NEW']


# ---------------------------------------------------------------------------
# file_lock — sanity for the lock-acquired-but-release-fails defensive branch
# ---------------------------------------------------------------------------


def test_logfire_client_proactive_refresh_before_request(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    # Token within the 60s refresh margin — `_maybe_refresh_before_request` should
    # rotate it before the actual HTTP call lands on the server.
    expiration = (datetime.now(tz=timezone.utc) + timedelta(seconds=5)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    user_token = collection.get_token(BASE_URL)
    client = LogfireClient(user_token=user_token, collection=collection)
    headers: list[str] = []

    def _record(request: Any, context: Any) -> Any:
        headers.append(str(request.headers.get('Authorization')))
        context.status_code = 200
        return {'ok': True}

    with requests_mock.Mocker() as m:
        m.get(f'{BASE_URL}/v1/test', json=_record)
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
        client._get_raw('/v1/test')  # pyright: ignore[reportPrivateUsage]
    assert headers == ['Bearer NEW']


def test_logfire_client_401_when_refresh_returns_same_token(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    """If refresh succeeds but the server keeps issuing the same access token,
    `_try_refresh` reports False and the original 401 propagates unchanged."""
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
    with requests_mock.Mocker() as m:
        m.get(f'{BASE_URL}/v1/test', status_code=401, text='unauthorized')
        m.get(METADATA_URL, json=_metadata())
        # Refresh returns the same access token → _try_refresh returns False →
        # the original 401 surfaces as UnexpectedResponse.
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
        with pytest.raises(Exception, match='401'):
            client._get_raw('/v1/test')  # pyright: ignore[reportPrivateUsage]


def test_logfire_client_post_raw_401_retry(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='OLD',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    user_token = collection.get_token(BASE_URL)
    client = LogfireClient(user_token=user_token, collection=collection)
    seen: list[str] = []

    def _respond(request: Any, context: Any) -> Any:
        seen.append(str(request.headers.get('Authorization')))
        if len(seen) == 1:
            context.status_code = 401
            return {}
        context.status_code = 200
        return {'created': True}

    with requests_mock.Mocker() as m:
        m.post(f'{BASE_URL}/v1/widgets', json=_respond)
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
        response = client._post_raw('/v1/widgets', body={'x': 1})  # pyright: ignore[reportPrivateUsage]
    assert response.json() == {'created': True}
    assert seen == ['Bearer OLD', 'Bearer NEW']


def test_logfire_client_get_wraps_errors(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
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
    client = LogfireClient(user_token=collection.get_token(BASE_URL), collection=collection)
    with requests_mock.Mocker() as m:
        m.get(f'{BASE_URL}/v1/ok', json={'ok': True})
        m.get(f'{BASE_URL}/v1/broken', status_code=500, text='boom')
        assert client._get('/v1/ok', error_message='nope') == {'ok': True}  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(LogfireConfigError, match='wrapped'):
            client._get('/v1/broken', error_message='wrapped')  # pyright: ignore[reportPrivateUsage]


def test_logfire_client_post_raw_success_without_retry(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    """Exercises the happy-path branch in `_post_raw` (non-401 response)."""
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
    client = LogfireClient(user_token=collection.get_token(BASE_URL), collection=collection)
    with requests_mock.Mocker() as m:
        m.post(f'{BASE_URL}/v1/widgets', json={'ok': True}, status_code=200)
        assert client._post_raw('/v1/widgets', body={}).json() == {'ok': True}  # pyright: ignore[reportPrivateUsage]


def test_try_refresh_returns_false_without_collection(tmp_path: Path, fake_keyring: _InMemoryKeyring) -> None:
    # Build a UserToken by hand (no collection wired in) and make sure a
    # forced refresh attempt reports failure cleanly instead of crashing.
    token = UserToken(
        token=SecretStr('AT'),
        base_url=BASE_URL,
        expiration=(datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat(),
        refresh_token=SecretStr('RT'),
    )
    client = LogfireClient(user_token=token, collection=None)
    assert client._try_refresh(force=True) is False  # pyright: ignore[reportPrivateUsage]


def test_logout_inline_oauth_without_keyring(tmp_path: Path, no_keyring: None) -> None:
    auth_file = tmp_path / 'default.toml'
    collection = UserTokenCollection(path=auth_file)
    expiration = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    # Without a keyring, tokens land inline and `keyring_service` is None —
    # exercises the logout branch that skips `storage.delete(...)`.
    collection.add_oauth_token(
        BASE_URL,
        client_id='logfire-cli',
        access_token='AT',
        refresh_token='RT',
        scope='project:read_dashboard',
        expiration=expiration,
    )
    collection.logout(BASE_URL)
    assert auth_file.read_text() == ''


def test_run_oauth_flow_uses_cached_dcr_client_id(
    tmp_path: Path, no_keyring: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seed an existing DCR record (no keyring -> inline tokens, no refresh_token).
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        f'[tokens."{BASE_URL}"]\n'
        'scope = "project:read_dashboard"\n'
        'expiration = "1970-01-01T00:00:00"\n'  # already expired
        'client_id = "dcr-cached"\n'
        f'registration_client_uri = "{BASE_URL}/oauth2/register/dcr-cached"\n'
        'oauth_token = ""\n'
        'refresh_token = ""\n'
    )
    monkeypatch.setattr('logfire._internal.auth.DEFAULT_FILE', auth_file)
    monkeypatch.setattr('logfire._internal.cli.auth.DEFAULT_FILE', auth_file)
    monkeypatch.setattr('builtins.input', _noop)
    monkeypatch.setattr('webbrowser.open', _noop)

    captured: dict[str, Any] = {}

    def device_handler(request: Any, context: Any) -> Any:
        text = str(request.text or '')
        form: dict[str, str] = dict(x.split('=', 1) for x in text.split('&'))
        captured.setdefault('first', form['client_id'])
        context.status_code = 200
        return {
            'device_code': 'DC',
            'user_code': 'UC',
            'verification_uri': 'http://x/',
            'interval': 0,
            'expires_in': 30,
        }

    with requests_mock.Mocker() as m:
        m.get(METADATA_URL, json=_metadata())
        m.post(DEVICE_URL, json=device_handler)
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
    # The cached DCR client id was used as the first attempt — DCR was *not* re-run.
    assert captured['first'] == 'dcr-cached'


def test_file_lock_nested_threads_share_lock_file(tmp_path: Path) -> None:
    path = tmp_path / 'default.toml'
    path.touch()
    entered = threading.Event()

    def worker() -> None:
        with file_lock(path):
            entered.set()

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)
    assert entered.is_set()
