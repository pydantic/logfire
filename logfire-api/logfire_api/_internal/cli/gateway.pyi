import argparse
import httpx
from .ai_tools import AiToolIntegration as AiToolIntegration, LOCAL_TOKEN_PLACEHOLDER as LOCAL_TOKEN_PLACEHOLDER, ai_tool_names as ai_tool_names, gateway_template_values as gateway_template_values, resolve_ai_tool as resolve_ai_tool
from .gateway_auth import CimdOAuthClient as CimdOAuthClient, GATEWAY_CIMD_PATH as GATEWAY_CIMD_PATH, GatewayAuth as GatewayAuth, GatewayError as GatewayError, OAuthSession as OAuthSession, discover_oauth_metadata as discover_oauth_metadata
from _typeshed import Incomplete
from dataclasses import dataclass
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from typing import Any, Literal

DEFAULT_PORT: int
DEFAULT_SCOPE: str
OAUTH_CALLBACK_PATH: str
console: Incomplete

@dataclass(frozen=True)
class GatewayRegion:
    backend: str
    gateway: str
    client_id: str

GATEWAY_REGIONS: dict[str, GatewayRegion]

@dataclass(frozen=True)
class GatewayCommandContext:
    raw_args: list[str]
    region: str | None
    logfire_url: str | None

@dataclass(frozen=True)
class GatewayCommand:
    name: Literal['usage', 'launch', 'serve']
    args: tuple[str, ...]

def filter_headers(headers: dict[str, str], *, direction: str) -> list[tuple[str, str]]: ...

@dataclass
class ProxyState:
    auth: GatewayAuth
    client: httpx.AsyncClient
    gateway: str
    region: str
    local_token: str

def build_app(state: ProxyState) -> Any: ...
def parse_gateway_command(context: GatewayCommandContext) -> GatewayCommand: ...
def execute_gateway_command(command: GatewayCommand, context: GatewayCommandContext) -> int: ...
def parse_gateway(args: argparse.Namespace) -> None:
    """Run a local OAuth proxy for the Logfire AI Gateway."""
