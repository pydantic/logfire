"""OAuth 2.1 Device Authorization Grant for `logfire auth --oauth`.

Implements:
- RFC 8414: OAuth 2.0 Authorization Server Metadata discovery.
- RFC 7636: PKCE (S256).
- RFC 8628: Device Authorization Grant.
- RFC 7591: Dynamic Client Registration — only used when the preregistered
  `logfire-cli` client is rejected *and* the server advertises a
  `registration_endpoint`.

The flow is driven by `run_device_flow`, which returns an `OAuthTokenResponse`
together with the `client_id` that actually produced it (may differ from the
default when DCR was used).
"""

from __future__ import annotations

import base64
import hashlib
import platform
import secrets
import sys
import time
import warnings
import webbrowser
from dataclasses import dataclass
from typing import Any, TypedDict, cast
from urllib.parse import urljoin, urlparse

import requests

from logfire.exceptions import LogfireConfigError

from .utils import UnexpectedResponse

DEFAULT_CLIENT_ID = 'logfire-cli'
"""Preregistered client id used by default for the OAuth device flow."""

DEFAULT_SCOPE = 'project:read_dashboard'
"""Default OAuth scope requested by the CLI."""

_METADATA_PATH = '/.well-known/oauth-authorization-server'


class OAuthServerMetadata(TypedDict, total=False):
    """Subset of RFC 8414 metadata used by this client."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    device_authorization_endpoint: str
    registration_endpoint: str
    scopes_supported: list[str]
    code_challenge_methods_supported: list[str]
    grant_types_supported: list[str]


class DeviceAuthResponse(TypedDict, total=False):
    """RFC 8628 §3.2 device authorization response."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class OAuthTokenResponse(TypedDict, total=False):
    """RFC 6749 token response (plus the RFC 8628 grant)."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str


@dataclass
class DynamicRegistration:
    """Outcome of an RFC 7591 Dynamic Client Registration request."""

    client_id: str
    registration_access_token: str | None = None
    registration_client_uri: str | None = None


@dataclass
class DeviceFlowResult:
    """Returned to the caller once the full device flow succeeds.

    `client_id` is the id that produced the token. When DCR was used,
    `registration_access_token` + `registration_client_uri` are the RFC 7592
    credentials needed to later deregister the client (`unregister_client`).
    For the preconfigured client they are `None`.
    """

    token: OAuthTokenResponse
    client_id: str
    registration_access_token: str | None = None
    registration_client_uri: str | None = None


def generate_pkce_pair() -> tuple[str, str]:
    """Return a random PKCE (verifier, S256 challenge) pair.

    Verifier: 43 characters (32 random bytes base64url-encoded, RFC 7636 §4.1).
    Challenge: BASE64URL(SHA256(verifier)) (RFC 7636 §4.2).
    """
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii').rstrip('=')
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return verifier, challenge


def discover_metadata(session: requests.Session, base_url: str) -> OAuthServerMetadata:
    """Fetch `/.well-known/oauth-authorization-server` from `base_url`."""
    url = urljoin(base_url.rstrip('/') + '/', _METADATA_PATH.lstrip('/'))
    try:
        response = session.get(url, timeout=15)
        UnexpectedResponse.raise_for_status(response)
    except requests.RequestException as e:
        raise LogfireConfigError(
            f'Failed to fetch OAuth server metadata from {url}. '
            'The Logfire instance may not support the OAuth 2.1 device flow; '
            'try `logfire auth` without `--oauth`.'
        ) from e
    return cast(OAuthServerMetadata, response.json())


def register_client(session: requests.Session, metadata: OAuthServerMetadata) -> DynamicRegistration:
    """Register a new OAuth client via RFC 7591 DCR.

    Returns the issued `client_id` together with the RFC 7592 management
    credentials (`registration_access_token` + `registration_client_uri`) when
    the server provides them. Raises `LogfireConfigError` if the server does
    not advertise a registration endpoint or the registration request fails.
    """
    endpoint = metadata.get('registration_endpoint')
    if not endpoint:
        raise LogfireConfigError(
            'The preregistered `logfire-cli` OAuth client was rejected, and the server '
            'does not expose a Dynamic Client Registration endpoint. Contact the Logfire '
            'administrator or fall back to `logfire auth` (without `--oauth`).'
        )
    payload = {
        'client_name': f'logfire-cli@{platform.node() or "unknown"}',
        'grant_types': ['urn:ietf:params:oauth:grant-type:device_code', 'refresh_token'],
        'token_endpoint_auth_method': 'none',
        'application_type': 'native',
    }
    try:
        response = session.post(endpoint, json=payload, timeout=15)
        UnexpectedResponse.raise_for_status(response)
    except requests.RequestException as e:
        raise LogfireConfigError('Failed to register an OAuth client with the Logfire server.') from e
    data = cast(dict[str, Any], response.json())
    client_id = data.get('client_id')
    if not client_id:
        raise LogfireConfigError('The dynamic client registration response did not include a `client_id`.')
    return DynamicRegistration(
        client_id=str(client_id),
        registration_access_token=data.get('registration_access_token'),
        registration_client_uri=data.get('registration_client_uri'),
    )


def unregister_client(
    session: requests.Session,
    *,
    registration_client_uri: str,
    registration_access_token: str,
) -> None:
    """Best-effort RFC 7592 Dynamic Client Deregistration (DELETE on the management URI).

    Swallows all network errors — deregistration is a courtesy cleanup on
    logout; failure should never abort the user-facing logout flow.
    """
    try:
        session.delete(
            registration_client_uri,
            headers={'Authorization': f'Bearer {registration_access_token}'},
            timeout=10,
        )
    except requests.RequestException:
        pass


def _post_form(session: requests.Session, url: str, data: dict[str, str]) -> requests.Response:
    return session.post(url, data=data, timeout=15, headers={'Accept': 'application/json'})


def _error_code(response: requests.Response) -> str:
    """Extract the OAuth error code (RFC 6749 §5.2) from an error response."""
    try:
        body: Any = response.json()
    except ValueError:
        return ''
    if not isinstance(body, dict):
        return ''
    body_dict = cast(dict[str, Any], body)
    error = body_dict.get('error')
    if isinstance(error, str):
        return error
    # Some proxies wrap the error response in `{"detail": {...}}`; handle that too.
    detail = body_dict.get('detail')
    if isinstance(detail, dict):
        nested = cast(dict[str, Any], detail).get('error')
        if isinstance(nested, str):
            return nested
    return ''


def request_device_authorization(
    session: requests.Session,
    metadata: OAuthServerMetadata,
    *,
    client_id: str,
    code_challenge: str,
    scope: str | None,
) -> tuple[DeviceAuthResponse, bool]:
    """Start the device flow.

    Returns `(response, invalid_client)`. When `invalid_client` is True, the
    caller may retry with a DCR-issued `client_id`.
    """
    endpoint = metadata.get('device_authorization_endpoint')
    if not endpoint:
        raise LogfireConfigError(
            'The OAuth server metadata does not declare a `device_authorization_endpoint`; '
            'this Logfire instance does not support the device flow.'
        )
    form = {
        'client_id': client_id,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    if scope:
        form['scope'] = scope
    response = _post_form(session, endpoint, form)
    if response.status_code == 401 or _error_code(response) == 'invalid_client':
        return cast(DeviceAuthResponse, {}), True
    try:
        UnexpectedResponse.raise_for_status(response)
    except UnexpectedResponse as e:
        raise LogfireConfigError('Failed to request OAuth device authorization.') from e
    return cast(DeviceAuthResponse, response.json()), False


def poll_for_token(
    session: requests.Session,
    metadata: OAuthServerMetadata,
    *,
    device_code: str,
    client_id: str,
    code_verifier: str,
    interval: int,
    expires_in: int,
    sleep: Any = time.sleep,
) -> OAuthTokenResponse | None:
    """Poll the token endpoint until the user completes authentication.

    Honors the RFC 8628 `authorization_pending`, `slow_down`, `access_denied`
    and `expired_token` error codes. Returns None if the user denied the
    request or the code expired.
    """
    token_endpoint = metadata.get('token_endpoint')
    if not token_endpoint:
        raise LogfireConfigError('The OAuth server metadata does not declare a `token_endpoint`.')
    grant = 'urn:ietf:params:oauth:grant-type:device_code'
    current_interval = max(1, interval)
    deadline = time.monotonic() + max(1, expires_in)
    while time.monotonic() < deadline:
        sleep(current_interval)
        response = _post_form(
            session,
            token_endpoint,
            {
                'grant_type': grant,
                'device_code': device_code,
                'client_id': client_id,
                'code_verifier': code_verifier,
            },
        )
        if response.status_code == 200:
            return cast(OAuthTokenResponse, response.json())
        error = _error_code(response)
        if error == 'authorization_pending':
            continue
        if error == 'slow_down':
            current_interval += 5
            continue
        if error == 'access_denied':
            sys.stderr.write('Authorization was denied by the user.\n')
            return None
        if error == 'expired_token':
            sys.stderr.write('The device code expired before authorization was completed.\n')
            return None
        # Any other error is fatal.
        raise LogfireConfigError(
            f'OAuth token endpoint returned an error while polling for the device code: {error or response.text!r}.'
        )
    sys.stderr.write('Timed out waiting for device-code authorization.\n')
    return None


def refresh_access_token(
    session: requests.Session,
    metadata: OAuthServerMetadata,
    *,
    refresh_token: str,
    client_id: str,
) -> OAuthTokenResponse:
    """Exchange a refresh token for a new access token (RFC 6749 §6)."""
    token_endpoint = metadata.get('token_endpoint')
    if not token_endpoint:
        raise LogfireConfigError('The OAuth server metadata does not declare a `token_endpoint`.')
    try:
        response = _post_form(
            session,
            token_endpoint,
            {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': client_id,
            },
        )
        UnexpectedResponse.raise_for_status(response)
    except UnexpectedResponse as e:
        raise LogfireConfigError('Failed to refresh the OAuth access token.') from e
    return cast(OAuthTokenResponse, response.json())


def run_device_flow(
    session: requests.Session,
    base_url: str,
    *,
    cached_client_id: str | None = None,
    scope: str | None = DEFAULT_SCOPE,
) -> DeviceFlowResult:
    """End-to-end OAuth 2.1 device flow against `base_url`.

    The client id is chosen automatically:

    1. `cached_client_id` (if given) — reuses a previously DCR-issued client.
    2. The preregistered `logfire-cli`.
    3. DCR via `registration_endpoint`, if (2) is rejected with `invalid_client`
       and the server advertises DCR.
    """
    metadata = discover_metadata(session, base_url)
    code_verifier, code_challenge = generate_pkce_pair()

    client_id = cached_client_id or DEFAULT_CLIENT_ID
    registration: DynamicRegistration | None = None
    device_response, invalid_client = request_device_authorization(
        session, metadata, client_id=client_id, code_challenge=code_challenge, scope=scope
    )
    if invalid_client:
        # Fall back to DCR only if the default client was rejected.
        registration = register_client(session, metadata)
        client_id = registration.client_id
        device_response, invalid_client = request_device_authorization(
            session, metadata, client_id=client_id, code_challenge=code_challenge, scope=scope
        )
        if invalid_client:
            raise LogfireConfigError('OAuth device authorization was rejected even after dynamic client registration.')

    verification_uri = device_response.get('verification_uri_complete') or device_response.get('verification_uri', '')
    user_code = device_response.get('user_code', '')
    verification_host = urlparse(verification_uri).netloc or verification_uri
    sys.stderr.write(f'First copy your one-time code: {user_code}\n')
    sys.stderr.write(f'Press Enter to open {verification_host} in your browser...\n')
    try:
        input()
    except EOFError:
        pass
    try:
        webbrowser.open(verification_uri, new=2)
    except webbrowser.Error:
        pass
    sys.stderr.write(
        f"Please open {verification_uri} in your browser to authenticate if it hasn't already.\n"
        'Waiting for you to authenticate with Logfire...\n'
    )

    token = poll_for_token(
        session,
        metadata,
        device_code=device_response.get('device_code', ''),
        client_id=client_id,
        code_verifier=code_verifier,
        interval=int(device_response.get('interval', 5)),
        expires_in=int(device_response.get('expires_in', 300)),
    )
    if token is None:
        raise LogfireConfigError('OAuth device authorization did not complete.')
    if 'refresh_token' not in token:
        warnings.warn(
            'The Logfire server did not return a refresh_token; the access token cannot be renewed automatically.'
        )
    return DeviceFlowResult(
        token=token,
        client_id=client_id,
        registration_access_token=registration.registration_access_token if registration else None,
        registration_client_uri=registration.registration_client_uri if registration else None,
    )
