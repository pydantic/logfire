from __future__ import annotations

import argparse
import asyncio
import contextlib
import html
import importlib
import json
import os
import secrets
import shutil
import socket
import sys
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from rich.console import Console
from rich.prompt import Prompt

from logfire.exceptions import LogfireConfigError

from .ai_tools import (
    LOCAL_TOKEN_PLACEHOLDER,
    AiToolIntegration,
    ai_tool_names,
    gateway_template_values,
    resolve_ai_tool,
)
from .gateway_auth import GATEWAY_CIMD_PATH, CimdOAuthClient, GatewayAuth, OAuthSession, discover_oauth_metadata

DEFAULT_PORT = 11465
DEFAULT_SCOPE = 'project:gateway_proxy'
OAUTH_CALLBACK_PATH = '/callback'

console = Console(stderr=True)


@dataclass(frozen=True)
class GatewayDeps:
    httpx: Any
    uvicorn: Any
    Starlette: Any
    Route: Any
    Response: Any
    JSONResponse: Any
    StreamingResponse: Any


def load_gateway_deps() -> GatewayDeps:
    """Load optional proxy dependencies, raising a user-facing error if absent."""
    try:
        httpx = importlib.import_module('httpx')
        uvicorn = importlib.import_module('uvicorn')
        starlette_applications = importlib.import_module('starlette.applications')
        starlette_responses = importlib.import_module('starlette.responses')
        starlette_routing = importlib.import_module('starlette.routing')
    except ImportError as exc:
        raise LogfireConfigError(
            'The `logfire gateway` command requires extra dependencies. Install them with:\n'
            '  pip install "logfire[gateway]"'
        ) from exc
    return GatewayDeps(
        httpx=httpx,
        uvicorn=uvicorn,
        Starlette=starlette_applications.Starlette,
        Route=starlette_routing.Route,
        Response=starlette_responses.Response,
        JSONResponse=starlette_responses.JSONResponse,
        StreamingResponse=starlette_responses.StreamingResponse,
    )


@dataclass(frozen=True)
class GatewayRegion:
    backend: str
    gateway: str


GATEWAY_REGIONS: dict[str, GatewayRegion] = {
    'us': GatewayRegion('https://logfire-us.pydantic.dev', 'https://gateway-us.pydantic.dev'),
    'eu': GatewayRegion('https://logfire-eu.pydantic.dev', 'https://gateway-eu.pydantic.dev'),
}


@dataclass(frozen=True)
class GatewayCommandContext:
    raw_args: list[str]
    region: str | None
    logfire_url: str | None


@dataclass(frozen=True)
class GatewayCommand:
    name: Literal['usage', 'launch', 'serve']
    args: tuple[str, ...]


_HOP_BY_HOP = frozenset(
    {
        'connection',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailers',
        'transfer-encoding',
        'upgrade',
        'host',
        'content-length',
    }
)
_REQUEST_DROP = frozenset({'authorization', 'x-api-key'})
_RESPONSE_DROP = frozenset({'content-encoding'})


def filter_headers(headers: dict[str, str], *, direction: str) -> list[tuple[str, str]]:
    extra_drop = _REQUEST_DROP if direction == 'request' else _RESPONSE_DROP
    filtered: list[tuple[str, str]] = []
    for key, value in headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP or lower in extra_drop:
            continue
        filtered.append((key, value))
    return filtered


@dataclass
class ProxyState:
    deps: GatewayDeps
    auth: GatewayAuth
    client: Any
    gateway: str
    region: str
    local_token: str


def _is_streaming(body: bytes) -> bool:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(parsed, dict):
        return False
    parsed_dict = cast(dict[str, Any], parsed)
    return parsed_dict.get('stream') is True


def _local_request_authorized(headers: Any, local_token: str) -> bool:
    authorization = headers.get('authorization') or ''
    scheme, _, value = authorization.partition(' ')
    if scheme.lower() == 'bearer' and secrets.compare_digest(value, local_token):
        return True
    api_key = headers.get('x-api-key') or ''
    return secrets.compare_digest(api_key, local_token)


async def _gateway_request(
    state: ProxyState, method: str, upstream_url: str, headers: dict[str, str], body: bytes
) -> tuple[int, Any, bytes, str]:
    response = None
    response_body = b''
    for attempt in range(3):
        token = await state.auth.current_access_token()
        request_headers = {**headers, 'Authorization': f'Bearer {token}'}
        response = await state.client.request(method, upstream_url, headers=request_headers, content=body)
        response_body = await response.aread()
        if response.status_code != 401:
            break
        if attempt == 2 or not await state.auth.recover_after_rejection(use_reauth=attempt >= 1):
            break
    if response is None:
        raise RuntimeError('gateway request was never sent')
    return response.status_code, response.headers, response_body, response.headers.get('content-type', '')


async def _gateway_stream(
    state: ProxyState, method: str, upstream_url: str, headers: dict[str, str], body: bytes
) -> Any:
    for attempt in range(3):
        token = await state.auth.current_access_token()
        request_headers = {**headers, 'Authorization': f'Bearer {token}'}
        request = state.client.build_request(method, upstream_url, headers=request_headers, content=body)
        response = await state.client.send(request, stream=True)
        if response.status_code != 401:
            return response
        if attempt == 2 or not await state.auth.recover_after_rejection(use_reauth=attempt >= 1):
            return response
        await response.aclose()
    raise RuntimeError('unreachable')


async def _handle_proxy(request: Any) -> Any:
    state: ProxyState = request.app.state.logfire_gateway
    deps = state.deps
    path = request.url.path
    if not path.startswith('/proxy/'):
        return deps.JSONResponse({'error': 'no route', 'path': path}, status_code=404)
    if not _local_request_authorized(request.headers, state.local_token):
        return deps.JSONResponse({'error': 'unauthorized'}, status_code=401)
    body = await request.body()
    upstream_url = f'{state.gateway.rstrip("/")}{path}'
    if request.url.query:
        upstream_url = f'{upstream_url}?{request.url.query}'
    headers = dict(filter_headers(dict(request.headers), direction='request'))

    if _is_streaming(body):
        upstream_response = await _gateway_stream(state, request.method, upstream_url, headers, body)

        async def body_iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_response.aiter_raw():
                    yield chunk
            finally:
                await upstream_response.aclose()

        return deps.StreamingResponse(
            body_iter(),
            status_code=upstream_response.status_code,
            headers=dict(filter_headers(dict(upstream_response.headers), direction='response')),
            media_type=upstream_response.headers.get('content-type'),
        )

    status, response_headers, response_body, content_type = await _gateway_request(
        state, request.method, upstream_url, headers, body
    )
    return deps.Response(
        content=response_body,
        status_code=status,
        headers=dict(filter_headers(dict(response_headers), direction='response')),
        media_type=content_type,
    )


_OAUTH_DONE_HTML = '<!doctype html><title>Logfire Gateway</title><h1>{title}</h1><p>{body}</p>'


def _oauth_done_html(title: str, body: str) -> str:
    return _OAUTH_DONE_HTML.format(title=html.escape(title), body=html.escape(body))


async def _handle_oauth_callback(request: Any) -> Any:
    state: ProxyState = request.app.state.logfire_gateway
    params = request.query_params
    result = state.auth.complete_browser_callback(
        error=params.get('error'),
        error_description=params.get('error_description'),
        code=params.get('code'),
        state=params.get('state'),
    )
    return state.deps.Response(
        _oauth_done_html(result.title, result.body),
        status_code=result.status_code,
        media_type='text/html',
    )


async def _handle_favicon(request: Any) -> Any:
    return request.app.state.logfire_gateway.deps.Response(status_code=204)


def build_app(deps: GatewayDeps, state: ProxyState) -> Any:
    app = deps.Starlette(
        routes=[
            deps.Route(OAUTH_CALLBACK_PATH, _handle_oauth_callback, methods=['GET']),
            deps.Route('/_logfire_gateway/oauth/callback', _handle_oauth_callback, methods=['GET']),
            deps.Route('/favicon.ico', _handle_favicon, methods=['GET']),
            deps.Route('/{path:path}', _handle_proxy, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
        ]
    )
    app.state.logfire_gateway = state
    return app


def _pick_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', preferred))
            return preferred
        except OSError:
            sock.bind(('127.0.0.1', 0))
            return int(sock.getsockname()[1])


def _oauth_redirect_uri(port: int) -> str:
    return f'http://127.0.0.1:{port}{OAUTH_CALLBACK_PATH}'


def _gateway_cimd_client_id(gateway: str) -> str:
    return f'{gateway.rstrip("/")}{GATEWAY_CIMD_PATH}'


@asynccontextmanager
async def _authorize_and_serve(
    *, deps: GatewayDeps, region: str, backend: str, gateway: str, scope: str, port: int, flow: str
) -> AsyncGenerator[tuple[ProxyState, str], None]:
    redirect_uri = _oauth_redirect_uri(port)
    resource = f'{gateway.rstrip("/")}/proxy'
    async with deps.httpx.AsyncClient(timeout=30.0) as control_client:
        metadata = await discover_oauth_metadata(control_client, backend)
        client = CimdOAuthClient(control_client, metadata, client_id=_gateway_cimd_client_id(gateway))
        session = OAuthSession(client, metadata, resource=resource, scope=scope)
        auth = GatewayAuth(session, redirect_uri=redirect_uri, flow=flow)
        async with deps.httpx.AsyncClient(timeout=180.0) as upstream_client:
            state = ProxyState(
                deps=deps,
                auth=auth,
                client=upstream_client,
                gateway=gateway.rstrip('/'),
                region=region,
                local_token=secrets.token_urlsafe(32),
            )
            app = build_app(deps, state)
            config = deps.uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)
            server = deps.uvicorn.Server(config)
            server_task = asyncio.create_task(server.serve())
            for _ in range(100):
                if server.started or server_task.done():
                    break
                await asyncio.sleep(0.05)
            try:
                if server_task.done():
                    await server_task
                if not server.started:
                    raise RuntimeError(f'Logfire Gateway proxy failed to start on 127.0.0.1:{port}')
                await auth.authorize()
                yield state, f'http://127.0.0.1:{port}'
            finally:
                server.should_exit = True
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(server_task, timeout=5.0)


def _gateway_urls(args: argparse.Namespace) -> tuple[str, str, str]:
    region_name = args.gateway_region
    preset = GATEWAY_REGIONS[region_name]
    backend = args.logfire_url or preset.backend
    gateway = args.gateway_url or os.getenv('LOGFIRE_GATEWAY_URL') or preset.gateway
    return region_name, backend.rstrip('/'), gateway.rstrip('/')


def _split_extra_args(args: list[str]) -> tuple[list[str], list[str]]:
    if '--' not in args:
        return args, []
    index = args.index('--')
    return args[:index], args[index + 1 :]


def _launch_epilog() -> str:
    names = ', '.join(sorted(ai_tool_names()))
    return f'Supported integrations: {names}'


def _parse_launch_args(raw: list[str], context: GatewayCommandContext) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='logfire gateway launch',
        description='Launch an AI coding tool through the Logfire AI Gateway.',
        epilog=_launch_epilog(),
    )
    parser.add_argument('integration', nargs='?', help='integration to launch')
    parser.add_argument('--model', default=None, help='model to pass to the selected integration')
    parser.add_argument('--config', action='store_true', help='print the integration configuration without launching')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--device-flow', action='store_true', help='use OAuth device flow instead of browser callback')
    parser.add_argument('--gateway-url', default=None, help='override the Logfire AI Gateway URL')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.set_defaults(logfire_url=context.logfire_url, gateway_region=context.region or 'us')
    return parser.parse_args(raw)


def _parse_serve_args(raw: list[str], context: GatewayCommandContext) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='logfire gateway serve',
        description='Run the Logfire AI Gateway local OAuth proxy without launching a child tool.',
    )
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--device-flow', action='store_true')
    parser.add_argument('--gateway-url', default=None, help='override the Logfire AI Gateway URL')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.set_defaults(logfire_url=context.logfire_url, gateway_region=context.region or 'us')
    return parser.parse_args(raw)


def _interactive_integration() -> str:
    installed = [name for name in ai_tool_names() if resolve_ai_tool(name).binary_path()]
    if not installed:
        console.print('[red]No supported integration binaries were found on PATH.[/]')
        raise SystemExit(127)
    return Prompt.ask('Launch which integration?', choices=installed, default=installed[0])


def _configure_only(integration: AiToolIntegration, *, region: str, model: str | None) -> None:
    console.print(f'{integration.display_name} ({integration.name})')
    console.print(f'  region: {region}')
    console.print(f'  model: {model or "<tool default>"}')
    binary = integration.binary_path()
    console.print(f'  binary: {binary or integration.binary + " (not found)"}')
    env = integration.build_gateway_env(
        proxy_base='http://127.0.0.1:PORT',
        model=model,
        workdir=Path(tempfile.gettempdir()) / 'logfire-gateway-example',
        local_token=LOCAL_TOKEN_PLACEHOLDER,
    )
    console.print('Environment:')
    for key, value in env.items():
        if value:
            console.print(f'  {key}={value}')
        else:
            console.print(f'  unset {key}')


def _run_launch(raw: list[str], context: GatewayCommandContext) -> int:
    pre, extra = _split_extra_args(raw)
    args = _parse_launch_args(pre, context)
    integration = resolve_ai_tool(args.integration or _interactive_integration())
    if args.config:
        _configure_only(integration, region=args.gateway_region, model=args.model)
        return 0
    if integration.binary_path() is None:
        console.print(f'[red]error:[/] {integration.display_name} binary {integration.binary!r} was not found on PATH.')
        return 127
    deps = load_gateway_deps()
    region, backend, gateway = _gateway_urls(args)
    port = _pick_port(args.port)
    return asyncio.run(
        _launch_async(
            deps=deps,
            integration=integration,
            extra=extra,
            region=region,
            backend=backend,
            gateway=gateway,
            scope=DEFAULT_SCOPE,
            port=port,
            model=args.model,
            flow='device' if args.device_flow else 'browser',
        )
    )


async def _launch_async(
    *,
    deps: GatewayDeps,
    integration: AiToolIntegration,
    extra: list[str],
    region: str,
    backend: str,
    gateway: str,
    scope: str,
    port: int,
    model: str | None,
    flow: str,
) -> int:
    binary = integration.binary_path()
    if binary is None:
        return 127
    async with _authorize_and_serve(
        deps=deps, region=region, backend=backend, gateway=gateway, scope=scope, port=port, flow=flow
    ) as (_state, proxy_base):
        workdir = Path(tempfile.mkdtemp(prefix='logfire-gateway-'))
        try:
            env = integration.build_gateway_env(
                proxy_base=proxy_base, model=model, workdir=workdir, local_token=_state.local_token
            )
            extra_args = integration.build_gateway_extra_args(proxy_base=proxy_base, model=model, workdir=workdir)
            console.print(f'[green]launching[/] {integration.display_name} through Logfire Gateway at {proxy_base}')
            if integration.notice:
                console.print(
                    f'[yellow]note:[/] {integration.notice.format(**gateway_template_values(proxy_base, _state.local_token))}'
                )
            process = await asyncio.create_subprocess_exec(binary, *extra_args, *extra, env={**os.environ, **env})
            return await process.wait()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


async def _run_serve_async(args: argparse.Namespace) -> int:
    deps = load_gateway_deps()
    region, backend, gateway = _gateway_urls(args)
    port = _pick_port(args.port)
    async with _authorize_and_serve(
        deps=deps,
        region=region,
        backend=backend,
        gateway=gateway,
        scope=DEFAULT_SCOPE,
        port=port,
        flow='device' if args.device_flow else 'browser',
    ) as (state, proxy_base):
        console.print()
        console.print(f'[bold green]Logfire Gateway proxy serving[/] at {proxy_base}')
        console.print(f'[dim]Forward OpenAI-compatible tools to {proxy_base}/proxy/openai/v1[/]')
        console.print(f'[dim]Forward Anthropic-compatible tools to {proxy_base}/proxy/anthropic[/]')
        console.print(f'[dim]Use API key:[/] {state.local_token}')
        console.print('[dim]Press Ctrl-C to exit[/]')
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            return 130


def _run_serve(raw: list[str], context: GatewayCommandContext) -> int:
    args = _parse_serve_args(raw, context)
    return asyncio.run(_run_serve_async(args))


def _gateway_usage() -> None:
    console.print(
        'usage: logfire gateway {launch,serve}\n\n'
        'Run AI coding tools through the Logfire AI Gateway using short-lived OAuth tokens.'
    )


def _is_gateway_usage_request(raw: list[str]) -> bool:
    return not raw or raw[0] in ('-h', '--help', 'help')


def parse_gateway_command(context: GatewayCommandContext) -> GatewayCommand:
    raw = context.raw_args
    if _is_gateway_usage_request(raw):
        return GatewayCommand('usage', ())
    command, rest = raw[0], raw[1:]
    if command == 'launch':
        return GatewayCommand('launch', tuple(rest))
    if command == 'serve':
        return GatewayCommand('serve', tuple(rest))
    # Convenience: `logfire gateway claude` means launch claude.
    return GatewayCommand('launch', tuple(raw))


def execute_gateway_command(command: GatewayCommand, context: GatewayCommandContext) -> int:
    if command.name == 'usage':
        _gateway_usage()
        return 0
    try:
        if command.name == 'launch':
            return _run_launch(list(command.args), context)
        return _run_serve(list(command.args), context)
    except LogfireConfigError as exc:
        sys.stderr.write(f'{exc}\n')
        return 1
    except KeyboardInterrupt:
        return 130


def run_gateway_command(context: GatewayCommandContext) -> int:
    return execute_gateway_command(parse_gateway_command(context), context)


def parse_gateway(args: argparse.Namespace) -> None:
    """Run a local OAuth proxy for the Logfire AI Gateway."""
    context = GatewayCommandContext(
        raw_args=list(args.gateway_args or []),
        region=args.region,
        logfire_url=args.logfire_url,
    )
    command = parse_gateway_command(context)
    code = execute_gateway_command(command, context)
    if command.name == 'usage':
        return
    raise SystemExit(code)
