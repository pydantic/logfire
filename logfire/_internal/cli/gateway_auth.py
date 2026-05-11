from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import secrets
import time
import webbrowser
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urlencode

from rich.console import Console

REFRESH_MARGIN_SECONDS = 120.0

console = Console(stderr=True)


@dataclass(frozen=True)
class OAuthMetadata:
    registration_endpoint: str
    authorization_endpoint: str
    token_endpoint: str
    device_authorization_endpoint: str


async def discover_oauth_metadata(http: Any, backend: str) -> OAuthMetadata:
    """Fetch the backend's OAuth authorization server metadata."""
    url = f'{backend.rstrip("/")}/.well-known/oauth-authorization-server'
    response = await http.get(url)
    if response.status_code != 200:
        raise RuntimeError(f'OAuth discovery failed ({response.status_code}): {url}')
    body = _json_dict(response)
    try:
        return OAuthMetadata(
            registration_endpoint=body['registration_endpoint'],
            authorization_endpoint=body['authorization_endpoint'],
            token_endpoint=body['token_endpoint'],
            device_authorization_endpoint=body['device_authorization_endpoint'],
        )
    except KeyError as exc:
        raise RuntimeError(f'OAuth discovery missing field {exc.args[0]!r} in {url}') from exc


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


def _json_dict(response: Any) -> dict[str, Any]:
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f'Expected JSON object response, got {type(body).__name__}')
    return cast(dict[str, Any], body)


class EphemeralDcrClient:
    """Disposable public OAuth client registered for one gateway proxy run."""

    def __init__(
        self,
        http: Any,
        metadata: OAuthMetadata,
        *,
        scope: str,
        cleanup_errors: tuple[type[BaseException], ...] = (RuntimeError, OSError, TimeoutError),
    ) -> None:
        self._http = http
        self._metadata = metadata
        self._scope = scope
        self._cleanup_errors = cleanup_errors
        self.client_id: str | None = None
        self._registration_access_token: str | None = None
        self._registration_uri: str | None = None

    async def register_for_flow(self, flow: str, *, redirect_uri: str | None = None) -> None:
        if flow == 'browser':
            if redirect_uri is None:
                raise RuntimeError('browser flow requires a redirect URI')
            grant_types = ['authorization_code', 'refresh_token']
            redirect_uris: list[str] | None = [redirect_uri]
        else:
            grant_types = ['urn:ietf:params:oauth:grant-type:device_code', 'refresh_token']
            redirect_uris = None

        body: dict[str, Any] = {
            'client_name': 'Logfire Gateway',
            'grant_types': grant_types,
            'token_endpoint_auth_method': 'none',
            'scope': self._scope,
        }
        if redirect_uris is not None:
            body['redirect_uris'] = redirect_uris

        response = await self._http.post(self._metadata.registration_endpoint, json=body)
        response.raise_for_status()
        data = _json_dict(response)
        self.client_id = data['client_id']
        self._registration_access_token = data['registration_access_token']
        self._registration_uri = data.get('registration_client_uri')

    async def start_device_authorization(self, data: dict[str, str]) -> Any:
        return await self._http.post(self._metadata.device_authorization_endpoint, data=data)

    async def post_token(self, data: dict[str, str]) -> Any:
        return await self._http.post(self._metadata.token_endpoint, data=data)

    async def unregister(self) -> None:
        if self._registration_uri is None or self._registration_access_token is None:
            return
        try:
            await self._http.delete(
                self._registration_uri,
                headers={'Authorization': f'Bearer {self._registration_access_token}'},
                timeout=10.0,
            )
        except self._cleanup_errors as exc:  # pragma: no cover - best-effort cleanup
            console.print(f'[yellow]OAuth client cleanup failed (non-fatal): {exc}[/]')
        finally:
            self.client_id = None
            self._registration_access_token = None
            self._registration_uri = None


@dataclass
class AuthBootstrap:
    redirect_uri: str
    expected_state: str = ''
    code_verifier: str = ''
    received_code: str | None = None
    error: str | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class OAuthCallbackResult:
    title: str
    body: str
    status_code: int = 200


class OAuthSession:
    """In-memory OAuth token state for the local gateway proxy."""

    def __init__(self, dcr: EphemeralDcrClient, metadata: OAuthMetadata, *, resource: str, scope: str) -> None:
        self._dcr = dcr
        self._metadata = metadata
        self._resource = resource
        self._scope = scope
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def token_ttl_s(self) -> float:
        return max(0.0, self._expires_at - time.time())

    async def auth_code_flow(self, bootstrap: AuthBootstrap) -> None:
        if self._dcr.client_id is None:
            raise RuntimeError('OAuth client is not registered')
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(32)
        bootstrap.code_verifier = verifier
        bootstrap.expected_state = state
        params = {
            'response_type': 'code',
            'client_id': self._dcr.client_id,
            'redirect_uri': bootstrap.redirect_uri,
            'scope': self._scope,
            'state': state,
            'resource': self._resource,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        }
        authorize_url = f'{self._metadata.authorization_endpoint}?{urlencode(params)}'
        console.print()
        console.print('[bold cyan]Opening browser to authorize Logfire Gateway...[/]')
        console.print(f'[dim]If it does not open, visit:[/] [underline]{authorize_url}[/]')
        console.print()
        with contextlib.suppress(webbrowser.Error):
            webbrowser.open(authorize_url)
        await asyncio.wait_for(bootstrap.event.wait(), timeout=600)
        if bootstrap.error is not None:
            raise RuntimeError(f'authorization failed: {bootstrap.error}')
        if bootstrap.received_code is None:
            raise RuntimeError('authorization completed without a code')
        await self._post_token(
            {
                'grant_type': 'authorization_code',
                'code': bootstrap.received_code,
                'client_id': self._dcr.client_id,
                'redirect_uri': bootstrap.redirect_uri,
                'code_verifier': verifier,
                'resource': self._resource,
            },
            error_prefix='token exchange failed',
        )
        console.print('[green]authorized[/]')

    async def device_flow(self) -> None:
        if self._dcr.client_id is None:
            raise RuntimeError('OAuth client is not registered')
        verifier, challenge = _pkce_pair()
        response = await self._dcr.start_device_authorization(
            data={
                'client_id': self._dcr.client_id,
                'resource': self._resource,
                'scope': self._scope,
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f'Device authorization failed ({response.status_code}): {response.text}')
        data = _json_dict(response)
        verification = data.get('verification_uri_complete') or data['verification_uri']
        console.print()
        console.print(
            f'[bold cyan]Open[/] [underline]{verification}[/] [bold cyan]and enter code:[/] [bold]{data["user_code"]}[/]'
        )
        console.print()
        with contextlib.suppress(webbrowser.Error):
            webbrowser.open(verification)
        deadline = time.time() + int(data['expires_in'])
        interval = int(data.get('interval', 5))
        while time.time() < deadline:
            await asyncio.sleep(interval)
            token_response = await self._dcr.post_token(
                data={
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                    'device_code': data['device_code'],
                    'client_id': self._dcr.client_id,
                    'code_verifier': verifier,
                    'resource': self._resource,
                },
            )
            if token_response.status_code == 200:
                self._store(_json_dict(token_response))
                console.print('[green]authorized[/]')
                return
            body = _safe_json_object(token_response)
            detail_value = body.get('detail', body)
            detail = cast(dict[str, Any], detail_value) if isinstance(detail_value, dict) else {}
            error = detail.get('error')
            if error == 'slow_down':
                interval += 5
            elif error == 'authorization_pending':
                continue
            else:
                raise RuntimeError(f'Device flow failed: {body}')
        raise RuntimeError('Device flow timed out')

    async def refresh(self) -> None:
        if self._dcr.client_id is None:
            raise RuntimeError('OAuth client is not registered')
        if self._refresh_token is None:
            raise RuntimeError('no refresh token; reauthorize')
        await self._post_token(
            {
                'grant_type': 'refresh_token',
                'refresh_token': self._refresh_token,
                'client_id': self._dcr.client_id,
                'resource': self._resource,
            },
            error_prefix='token refresh failed',
        )

    async def current_access_token(self) -> str:
        async with self._lock:
            if self._access_token is None:
                raise RuntimeError('gateway proxy used before authorization completed')
            if self._expires_at - time.time() < REFRESH_MARGIN_SECONDS:
                await self.refresh()
            return self._access_token

    async def force_refresh(self) -> str:
        async with self._lock:
            await self.refresh()
            if self._access_token is None:
                raise RuntimeError('refresh did not return an access token')
            return self._access_token

    async def _post_token(self, data: dict[str, str], *, error_prefix: str) -> None:
        response = await self._dcr.post_token(data)
        if response.status_code != 200:
            raise RuntimeError(f'{error_prefix} ({response.status_code}): {response.text}')
        self._store(_json_dict(response))

    def _store(self, body: dict[str, Any]) -> None:
        self._access_token = body['access_token']
        self._refresh_token = body.get('refresh_token', self._refresh_token)
        self._expires_at = time.time() + int(body.get('expires_in', 3600))


class GatewayAuth:
    """OAuth control-plane for an authorized local gateway proxy session."""

    def __init__(self, session: OAuthSession, *, redirect_uri: str, flow: str) -> None:
        self._session = session
        self._redirect_uri = redirect_uri
        self._flow = flow
        self._auth_bootstrap: AuthBootstrap | None = None
        self._reauth_lock = asyncio.Lock()

    @property
    def token_ttl_s(self) -> float:
        return self._session.token_ttl_s

    async def authorize(self) -> None:
        if self._flow == 'browser':
            bootstrap = AuthBootstrap(redirect_uri=self._redirect_uri)
            self._auth_bootstrap = bootstrap
            try:
                await self._session.auth_code_flow(bootstrap)
            finally:
                self._auth_bootstrap = None
        else:
            await self._session.device_flow()

    async def current_access_token(self) -> str:
        return await self._session.current_access_token()

    async def recover_after_rejection(self, *, use_reauth: bool) -> bool:
        if not use_reauth:
            try:
                await self._session.force_refresh()
            except RuntimeError:
                return False
            return True
        try:
            await self.reauthorize()
        except RuntimeError:
            return False
        return True

    async def reauthorize(self) -> None:
        async with self._reauth_lock:
            console.print('[yellow]Logfire Gateway token was rejected; reauthorizing...[/]')
            await self.authorize()

    def complete_browser_callback(
        self, *, error: str | None, error_description: str | None, code: str | None, state: str | None
    ) -> OAuthCallbackResult:
        bootstrap = self._auth_bootstrap
        if bootstrap is None or bootstrap.event.is_set():
            return OAuthCallbackResult('No pending authorization', 'Return to the terminal.', status_code=400)
        if error:
            bootstrap.error = f'{error}: {error_description or ""}'
            bootstrap.event.set()
            return OAuthCallbackResult('Authorization failed', bootstrap.error, status_code=400)
        if not code or state != bootstrap.expected_state:
            bootstrap.error = 'invalid or missing code/state'
            bootstrap.event.set()
            return OAuthCallbackResult('Authorization failed', bootstrap.error, status_code=400)
        bootstrap.received_code = code
        bootstrap.event.set()
        return OAuthCallbackResult('Authorized', 'You can close this tab and return to the terminal.')


def _safe_json_object(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return {'raw': response.text}
    return cast(dict[str, Any], body) if isinstance(body, dict) else {'raw': body}
