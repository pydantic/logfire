from __future__ import annotations

import platform
import re
import stat
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict, Union, cast
from urllib.parse import urljoin

import requests
from rich.console import Console
from rich.prompt import IntPrompt
from typing_extensions import Self

from logfire.exceptions import LogfireConfigError

from . import oauth as _oauth
from .token_storage import SecretStr, StoredOAuthSecrets, TokenStorage, file_lock
from .utils import UnexpectedResponse, read_toml_file

HOME_LOGFIRE = Path.home() / '.logfire'
"""Folder used to store global configuration, and user tokens."""
DEFAULT_FILE = HOME_LOGFIRE / 'default.toml'
"""File used to store user tokens."""

REFRESH_MARGIN = timedelta(seconds=60)
"""Refresh OAuth access tokens this long before they actually expire."""


PYDANTIC_LOGFIRE_TOKEN_PATTERN = re.compile(
    r'^(?P<safe_part>pylf_v(?P<version>[0-9]+)_(?P<region>[a-z]+)_)(?P<token>[a-zA-Z0-9]+)$'
)


class _RegionData(TypedDict):
    base_url: str
    gcp_region: str


REGIONS: dict[str, _RegionData] = {
    'us': {
        'base_url': 'https://logfire-us.pydantic.dev',
        'gcp_region': 'us-east4',
    },
    'eu': {
        'base_url': 'https://logfire-eu.pydantic.dev',
        'gcp_region': 'europe-west4',
    },
}
"""The existing Logfire regions."""


DEFAULT_OAUTH_CLIENT_ID = 'logfire-cli'
"""Preconfigured OAuth client id. Not persisted to TOML — used when a record is missing one."""


class UserTokenData(TypedDict):
    """Legacy long-lived user token record.

    Identified in TOML by the presence of the ``token`` key.
    """

    token: str
    expiration: str


class _OAuthRequired(TypedDict):
    """Fields required on every OAuth record."""

    expiration: str


class OAuthUserTokenData(_OAuthRequired, total=False):
    """OAuth 2.1 device-flow token record.

    The presence of inline ``oauth_token`` + ``refresh_token`` marks a
    file-only record (written when the OS keyring is unavailable); their
    absence means the secrets live in the keyring under `KEYRING_SERVICE`
    with the base URL as the username.

    ``client_id`` is persisted only for DCR-registered clients; preconfigured
    installs reuse the default `logfire-cli` id at load time. The
    ``registration_client_uri`` is the RFC 7592 management URL and only
    appears for DCR records — its presence flags a record that should be
    deregistered on logout.
    """

    scope: str
    client_id: str
    registration_client_uri: str
    oauth_token: str
    refresh_token: str


TokenRecord = Union[UserTokenData, OAuthUserTokenData]
"""Union of the two disk record shapes. Legacy records carry ``token``; OAuth records don't."""


class UserTokensFileData(TypedDict, total=False):
    """Content of the file containing the user tokens."""

    tokens: dict[str, TokenRecord]


@dataclass
class UserToken:
    """A user token — either a legacy long-lived token or an OAuth access token.

    The record kind is discriminated by the shape of the data rather than by a
    tag field: if ``refresh_token`` is non-``None`` the token was issued via
    the OAuth device flow, otherwise it's a legacy long-lived credential.
    """

    token: SecretStr
    base_url: str
    expiration: str
    client_id: str = DEFAULT_OAUTH_CLIENT_ID
    refresh_token: SecretStr | None = None
    scope: str | None = None
    # True when the secret tokens live in the OS keyring instead of inline in
    # the TOML file. Serialization just omits the inline fields — the keyring
    # entry is addressed by `(KEYRING_SERVICE, base_url)`.
    keyring_backed: bool = False
    # RFC 7592 management URL — present only for DCR-registered clients; drives
    # optional deregistration on logout.
    registration_client_uri: str | None = None
    registration_access_token: SecretStr | None = field(default=None, repr=False)

    @property
    def auth_method(self) -> Literal['oauth', 'user_token']:
        """Derived discriminator for the record kind.

        ``'oauth'`` for OAuth device-flow records (refresh token on file),
        ``'user_token'`` for legacy long-lived user tokens.
        """
        return 'oauth' if self.refresh_token is not None else 'user_token'

    @property
    def is_dcr_client(self) -> bool:
        """Whether the OAuth client was registered dynamically (vs. the preconfigured one)."""
        return self.registration_client_uri is not None

    @classmethod
    def from_user_token_data(cls, base_url: str, token: UserTokenData) -> Self:
        return cls(
            token=SecretStr(token['token']),
            base_url=base_url,
            expiration=token['expiration'],
        )

    @classmethod
    def from_oauth_record(
        cls,
        base_url: str,
        record: OAuthUserTokenData,
        storage: TokenStorage,
    ) -> Self | None:
        """Rehydrate an OAuth token, pulling secrets from keyring when needed.

        Returns None when the record references a keyring entry that can no
        longer be read (e.g. the keyring was disabled between logins).
        """
        # Records with inline tokens are file-backed; everything else is
        # keyring-backed (regardless of what service name we used originally).
        keyring_backed = 'oauth_token' not in record
        registration_access_token: SecretStr | None = None
        if keyring_backed:
            secrets = storage.load(base_url)
            if secrets is None:
                return None
            access_token_str = secrets.access_token
            refresh_token_str: str | None = secrets.refresh_token
            if secrets.registration_access_token:
                registration_access_token = SecretStr(secrets.registration_access_token)
        else:
            access_token_str = record.get('oauth_token', '')
            refresh_token_str = record.get('refresh_token') or ''
        return cls(
            token=SecretStr(access_token_str),
            base_url=base_url,
            expiration=record.get('expiration', ''),
            client_id=record.get('client_id') or DEFAULT_OAUTH_CLIENT_ID,
            refresh_token=SecretStr(refresh_token_str) if refresh_token_str else SecretStr(''),
            scope=record.get('scope'),
            keyring_backed=keyring_backed,
            registration_client_uri=record.get('registration_client_uri'),
            registration_access_token=registration_access_token,
        )

    @property
    def is_expired(self) -> bool:
        """Whether the token is expired."""
        return datetime.now(tz=timezone.utc) >= self._expiration_dt

    @property
    def needs_refresh(self) -> bool:
        """True if an OAuth token is within the refresh margin of expiring."""
        if self.auth_method != 'oauth' or not self.refresh_token:
            return False
        return datetime.now(tz=timezone.utc) + REFRESH_MARGIN >= self._expiration_dt

    @property
    def _expiration_dt(self) -> datetime:
        return datetime.fromisoformat(self.expiration.rstrip('Z')).replace(tzinfo=timezone.utc)

    @property
    def header_value(self) -> str:
        """The value to send in the Authorization header.

        Legacy long-lived tokens are sent raw to preserve backend compatibility;
        OAuth access tokens use the standard `Bearer` scheme.
        """
        raw = self.token.get_secret_value()
        if self.auth_method == 'oauth':
            return f'Bearer {raw}'
        return raw

    def __str__(self) -> str:
        region = 'us'
        raw = self.token.get_secret_value()
        if self.auth_method == 'oauth':
            prefix = f'OAuth ({self.base_url}) - '
            suffix = (raw[:5] if raw else '') + '****'
            return prefix + suffix

        if match := PYDANTIC_LOGFIRE_TOKEN_PATTERN.match(raw):
            region = match.group('region')
            if region not in REGIONS:
                region = 'us'

        token_repr = f'{region.upper()} ({self.base_url}) - '
        if match:
            token_repr += match.group('safe_part') + match.group('token')[:5]
        else:
            token_repr += raw[:5]
        token_repr += '****'
        return token_repr


def _is_legacy_record(raw: dict[str, Any]) -> bool:
    """A record is legacy if and only if it carries a raw long-lived ``token``."""
    return 'token' in raw


@dataclass
class UserTokenCollection:
    """A collection of user tokens, read from a user tokens file.

    Args:
        path: The path where the user tokens will be stored. If the path doesn't exist,
            an empty collection is created. Defaults to `~/.logfire/default.toml`.
    """

    user_tokens: dict[str, UserToken]
    """A mapping between base URLs and user tokens."""

    path: Path
    """The path where the user tokens are stored."""

    storage: TokenStorage
    """Keyring-backed secret storage used for OAuth records."""

    def __init__(self, path: Path | None = None, storage: TokenStorage | None = None) -> None:
        # FIXME: we can't set the default value of `path` to `DEFAULT_FILE`, otherwise
        # `mock.patch()` doesn't work:
        self.path = path if path is not None else DEFAULT_FILE
        self.storage = storage if storage is not None else TokenStorage()
        self.user_tokens = {}
        self._reload()

    def _reload(self) -> None:
        try:
            data = read_toml_file(self.path)
        except FileNotFoundError:
            data = {}
        raw_tokens = cast('dict[str, dict[str, Any]]', data.get('tokens', {}))
        tokens: dict[str, UserToken] = {}
        for url, raw in raw_tokens.items():
            if _is_legacy_record(raw):
                tokens[url] = UserToken.from_user_token_data(url, cast(UserTokenData, raw))
            else:
                token = UserToken.from_oauth_record(url, cast(OAuthUserTokenData, raw), self.storage)
                if token is not None:
                    tokens[url] = token
        self.user_tokens = tokens

    def get_token(self, base_url: str | None = None) -> UserToken:
        """Get a user token from the collection.

        Args:
            base_url: Only look for user tokens valid for this base URL. If not provided,
                all the tokens of the collection will be considered: if only one token is
                available, it will be used, otherwise the user will be prompted to choose
                a token.

        Raises:
            LogfireConfigError: If no user token is found (no token matched the base URL,
                the collection is empty, or the selected token is expired).
        """
        tokens_list = list(self.user_tokens.values())

        if base_url is not None:
            token = self.user_tokens.get(base_url)
            if token is None:
                raise LogfireConfigError(
                    f'No user token was found matching the {base_url} Logfire URL. '
                    'Please run `logfire auth` to authenticate.'
                )
        elif len(tokens_list) == 1:
            token = tokens_list[0]
        elif len(tokens_list) >= 2:
            choices_str = '\n'.join(
                f'{i}. {token} ({"expired" if token.is_expired else "valid"})'
                for i, token in enumerate(tokens_list, start=1)
            )
            int_choice = IntPrompt.ask(
                f'Multiple user tokens found. Please select one:\n{choices_str}\n',
                choices=[str(i) for i in range(1, len(tokens_list) + 1)],
                console=Console(file=sys.stderr),
            )
            token = tokens_list[int_choice - 1]
        else:  # tokens_list == []
            raise LogfireConfigError('You are not logged into Logfire. Please run `logfire auth` to authenticate.')

        if token.is_expired and token.auth_method != 'oauth':
            raise LogfireConfigError(f'User token {token} is expired. Please run `logfire auth` to authenticate.')
        return token

    def is_logged_in(self, base_url: str | None = None) -> bool:
        """Check whether the user token collection contains at least one valid user token.

        Args:
            base_url: Only check for user tokens valid for this base URL. If not provided,
                all the tokens of the collection will be considered.
        """
        if base_url is not None:
            tokens = (t for t in self.user_tokens.values() if t.base_url == base_url)
        else:
            tokens = self.user_tokens.values()

        def _valid(t: UserToken) -> bool:
            if not t.is_expired:
                return True
            # OAuth tokens are still usable while a refresh_token is available.
            return t.auth_method == 'oauth' and bool(t.refresh_token)

        return any(_valid(t) for t in tokens)

    def add_token(self, base_url: str, token: UserTokenData) -> UserToken:
        """Add a legacy long-lived user token to the collection."""
        self.user_tokens[base_url] = user_token = UserToken.from_user_token_data(base_url, token)
        self._dump()
        return user_token

    def add_oauth_token(
        self,
        base_url: str,
        *,
        client_id: str,
        access_token: str,
        refresh_token: str,
        scope: str,
        expiration: str,
        registration_access_token: str | None = None,
        registration_client_uri: str | None = None,
    ) -> UserToken:
        """Store an OAuth access/refresh token pair for `base_url`.

        Secrets are pushed into the OS keyring when available; otherwise they
        land in the TOML file which is then chmod-ed to 0600. DCR-issued
        clients additionally persist the RFC 7592 management credentials so
        that `logout` can deregister them.
        """
        secrets = StoredOAuthSecrets(
            access_token=access_token,
            refresh_token=refresh_token,
            registration_access_token=registration_access_token,
        )
        keyring_backed = self.storage.save(base_url, secrets)
        self.user_tokens[base_url] = user_token = UserToken(
            token=SecretStr(access_token),
            base_url=base_url,
            expiration=expiration,
            client_id=client_id,
            refresh_token=SecretStr(refresh_token),
            scope=scope,
            keyring_backed=keyring_backed,
            registration_client_uri=registration_client_uri,
            registration_access_token=SecretStr(registration_access_token) if registration_access_token else None,
        )
        self._dump()
        return user_token

    def logout(
        self,
        base_url: str | None = None,
        *,
        session: requests.Session | None = None,
    ) -> list[str]:
        """Remove user token(s) from the collection.

        When ``session`` is supplied and a removed record was a
        dynamically-registered OAuth client, this will also send a best-effort
        RFC 7592 DELETE to the server to deregister that client. The
        preconfigured ``logfire-cli`` is never deregistered.
        """
        if not self.user_tokens:
            raise LogfireConfigError('You are not logged into Logfire. Please run `logfire auth` to authenticate.')

        if base_url is not None and base_url not in self.user_tokens:
            raise LogfireConfigError(
                f'No user token was found matching the {base_url} Logfire URL. '
                'Please run `logfire auth` to authenticate.'
            )

        removed = [base_url] if base_url is not None else list(self.user_tokens.keys())
        for url in removed:
            token = self.user_tokens.pop(url)
            if token.auth_method != 'oauth':
                continue
            if session is not None and token.is_dcr_client and token.registration_access_token is not None:
                assert token.registration_client_uri is not None
                _oauth.unregister_client(
                    session,
                    registration_client_uri=token.registration_client_uri,
                    registration_access_token=token.registration_access_token.get_secret_value(),
                )
            if token.keyring_backed:
                self.storage.delete(url)

        self._dump()
        return removed

    def refresh_if_needed(
        self,
        token: UserToken,
        session: requests.Session,
        *,
        force: bool = False,
    ) -> UserToken:
        """Refresh `token` in place if it is (close to) expired.

        Serialized across processes via an advisory lock on the tokens file so
        that concurrent `logfire` commands cannot race each other into
        invalidating a refresh token. After acquiring the lock we re-read the
        on-disk record first: if another process already rotated the token we
        simply reuse its result.

        Pass ``force=True`` to rotate even when the token is not yet near
        expiry — used by the HTTP client after a server-side 401, where we
        have positive evidence the access token is no longer accepted.
        """
        if token.auth_method != 'oauth' or not token.refresh_token or not token.client_id:
            return token
        if not force and not token.needs_refresh:
            return token

        with file_lock(self.path):
            self._reload()
            current = self.user_tokens.get(token.base_url)
            # Reuse another process's result only when it actually replaced the
            # token we came in with — otherwise we'd skip the forced rotation.
            if (
                current is not None
                and current.auth_method == 'oauth'
                and not current.needs_refresh
                and current.token != token.token
            ):
                # Another process already refreshed. Update the caller's view.
                token.token = current.token
                token.refresh_token = current.refresh_token
                token.expiration = current.expiration
                return current

            refresh_target = current if current is not None else token
            metadata = _oauth.discover_metadata(session, refresh_target.base_url)
            assert refresh_target.refresh_token is not None
            response = _oauth.refresh_access_token(
                session,
                metadata,
                refresh_token=refresh_target.refresh_token.get_secret_value(),
                client_id=refresh_target.client_id,
            )
            new_expiration = (
                datetime.now(tz=timezone.utc) + timedelta(seconds=int(response.get('expires_in', 3600)))
            ).isoformat()
            new_refresh = response.get('refresh_token') or refresh_target.refresh_token.get_secret_value()
            new_access = response.get('access_token') or ''
            if not new_access:
                raise LogfireConfigError('The OAuth refresh response did not include an access_token.')
            registration_access_token = (
                refresh_target.registration_access_token.get_secret_value()
                if refresh_target.registration_access_token is not None
                else None
            )
            updated = self.add_oauth_token(
                refresh_target.base_url,
                client_id=refresh_target.client_id,
                access_token=new_access,
                refresh_token=new_refresh,
                scope=response.get('scope') or refresh_target.scope or '',
                expiration=new_expiration,
                registration_access_token=registration_access_token,
                registration_client_uri=refresh_target.registration_client_uri,
            )
            # Reflect the update into the caller-visible object.
            token.token = updated.token
            token.refresh_token = updated.refresh_token
            token.expiration = updated.expiration
            token.scope = updated.scope
            token.keyring_backed = updated.keyring_backed
            return updated

    def _dump(self) -> None:
        """Dump the user token collection as TOML to the provided path."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # There's no standard library package to write TOML files, so we'll write it manually.
        any_inline_secret = False
        with self.path.open('w') as f:
            for base_url, user_token in self.user_tokens.items():
                f.write(f'[tokens."{base_url}"]\n')
                if user_token.auth_method == 'oauth':
                    # Record shape is self-describing:
                    #   - `token = ...`        -> legacy user token
                    #   - `oauth_token = ...`  -> OAuth, tokens inline
                    #   - neither              -> OAuth, tokens in the keyring
                    f.write(f'scope = "{user_token.scope or ""}"\n')
                    f.write(f'expiration = "{user_token.expiration}"\n')
                    # Only persist the client_id for DCR-registered clients; the
                    # preconfigured `logfire-cli` id is the load-time default.
                    if user_token.is_dcr_client:
                        f.write(f'client_id = "{user_token.client_id}"\n')
                        assert user_token.registration_client_uri is not None
                        f.write(f'registration_client_uri = "{user_token.registration_client_uri}"\n')
                    if not user_token.keyring_backed:
                        # Keyring unavailable — persist tokens inline.
                        f.write(f'oauth_token = "{user_token.token.get_secret_value()}"\n')
                        refresh_raw = user_token.refresh_token.get_secret_value() if user_token.refresh_token else ''
                        f.write(f'refresh_token = "{refresh_raw}"\n')
                        any_inline_secret = True
                else:
                    f.write(f'token = "{user_token.token.get_secret_value()}"\n')
                    f.write(f'expiration = "{user_token.expiration}"\n')
        # If we ended up writing secrets to disk, make sure the file is not world-readable.
        if any_inline_secret:
            try:
                self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:  # pragma: no cover — best-effort on unusual filesystems
                pass


class NewDeviceFlow(TypedDict):
    """Matches model of the same name in the backend."""

    device_code: str
    frontend_auth_url: str


def request_device_code(session: requests.Session, base_api_url: str) -> tuple[str, str]:
    """Request a device code from the Logfire API.

    Args:
        session: The `requests` session to use.
        base_api_url: The base URL of the Logfire instance.

    Returns:
    return data['device_code'], data['frontend_auth_url']
        The device code and the frontend URL to authenticate the device at, as a `NewDeviceFlow` dict.
    """
    machine_name = platform.uname()[1]
    device_auth_endpoint = urljoin(base_api_url, '/v1/device-auth/new/')
    try:
        res = session.post(device_auth_endpoint, params={'machine_name': machine_name})
        UnexpectedResponse.raise_for_status(res)
    except requests.RequestException as e:  # pragma: no cover
        raise LogfireConfigError('Failed to request a device code.') from e
    data: NewDeviceFlow = res.json()
    return data['device_code'], data['frontend_auth_url']


def poll_for_token(session: requests.Session, device_code: str, base_api_url: str) -> UserTokenData:
    """Poll the Logfire API for the user token.

    This function will keep polling the API until it receives a user token, not that
    each request should take ~10 seconds as the API endpoint will block waiting for the user to
    complete authentication.

    Args:
        session: The `requests` session to use.
        device_code: The device code to poll for.
        base_api_url: The base URL of the Logfire instance.

    Returns:
        The user token.
    """
    auth_endpoint = urljoin(base_api_url, f'/v1/device-auth/wait/{device_code}')
    errors = 0
    while True:
        try:
            res = session.get(auth_endpoint, timeout=15)
            UnexpectedResponse.raise_for_status(res)
        except requests.RequestException as e:
            errors += 1
            if errors >= 4:
                raise LogfireConfigError('Failed to poll for token.') from e
            warnings.warn('Failed to poll for token. Retrying...')
        else:
            opt_user_token: UserTokenData | None = res.json()
            if opt_user_token:
                return opt_user_token


__all__ = [
    'DEFAULT_FILE',
    'HOME_LOGFIRE',
    'REGIONS',
    'OAuthUserTokenData',
    'UserToken',
    'UserTokenCollection',
    'UserTokenData',
    'poll_for_token',
    'request_device_code',
]
