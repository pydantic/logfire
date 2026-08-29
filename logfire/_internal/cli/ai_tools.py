from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, cast

from rich.console import Console

from logfire._internal.utils import read_toml_file
from logfire.exceptions import LogfireConfigError

LOCAL_TOKEN_PLACEHOLDER = '<generated-local-gateway-token>'

LOGFIRE_MCP_TOML = """
[mcp_servers.logfire]
url = "{url}"
"""


@dataclass(frozen=True)
class AiToolIntegration:
    name: str
    display_name: str
    binary: str
    # `None` means the tool cannot be launched through the Logfire AI Gateway, the same way
    # `configure_mcp=None` means it cannot be pointed at the Logfire MCP server. Both capabilities
    # are optional and are checked before use rather than assumed.
    env: dict[str, str] | None = None
    model_env: dict[str, str] = field(default_factory=dict[str, str])
    setup: Callable[[str, str | None, Path, str], dict[str, str]] | None = None
    configure_mcp: Callable[[str, Console, bool], None] | None = None
    description: str = ''
    notice: str = ''

    def binary_path(self) -> str | None:
        return shutil.which(self.binary)

    def supports_gateway(self) -> bool:
        return self.env is not None

    def build_gateway_env(
        self, *, proxy_base: str, model: str | None, workdir: Path, local_token: str
    ) -> dict[str, str]:
        if self.env is None:
            raise LogfireConfigError(f'{self.display_name} does not support the Logfire AI Gateway.')
        values = gateway_template_values(proxy_base, local_token)
        effective_model = model
        env: dict[str, str] = {}
        for key, value in self.env.items():
            env[key] = value.format(**values) if value else ''
        if effective_model is not None:
            for key, value in self.model_env.items():
                env[key] = value.format(model=effective_model)
        if self.setup is not None:
            env.update(self.setup(values['base'], effective_model, workdir, local_token))
        return env

    def configure_mcp_server(self, *, mcp_url: str, console: Console, update: bool) -> None:
        if self.configure_mcp is None:
            raise LogfireConfigError(f'{self.display_name} does not support Logfire MCP configuration.')
        if not self.binary_path():
            console.print(
                f'{self.binary} is not installed. Install `{self.binary}`, or remove the `--{self.name}` flag.'
            )
            raise SystemExit(1)
        self.configure_mcp(mcp_url, console, update)


def gateway_template_values(proxy_base: str, local_token: str) -> dict[str, str]:
    base = proxy_base.rstrip('/')
    return {
        'base': base,
        'local_token': local_token,
        'openai': f'{base}/proxy/openai',
        'openai_v1': f'{base}/proxy/openai/v1',
        'anthropic': f'{base}/proxy/anthropic',
        'google_vertex': f'{base}/proxy/google-vertex',
        'groq': f'{base}/proxy/groq',
    }


def resolve_ai_tool(name: str) -> AiToolIntegration:
    key = name.strip().lower()
    if key in AI_TOOL_INTEGRATIONS:
        return AI_TOOL_INTEGRATIONS[key]
    raise SystemExit(f'unknown AI tool integration: {name!r}. Available: {", ".join(sorted(AI_TOOL_INTEGRATIONS))}')


def ai_tool_names() -> tuple[str, ...]:
    return tuple(AI_TOOL_INTEGRATIONS)


def gateway_ai_tool_names() -> tuple[str, ...]:
    """Names of the tools that can be launched through the Logfire AI Gateway."""
    return tuple(name for name, tool in AI_TOOL_INTEGRATIONS.items() if tool.supports_gateway())


def mcp_ai_tool_names() -> tuple[str, ...]:
    """Names of the tools whose MCP configuration `logfire prompt` can write."""
    return tuple(name for name, tool in AI_TOOL_INTEGRATIONS.items() if tool.configure_mcp is not None)


def _opencode_gateway_setup(base: str, model: str | None, workdir: Path, local_token: str) -> dict[str, str]:
    config_path = workdir / 'opencode.jsonc'
    provider_config: dict[str, Any] = {
        'npm': '@ai-sdk/openai-compatible',
        'name': 'Logfire Gateway',
        'options': {'baseURL': f'{base}/proxy/openai/v1', 'apiKey': local_token},
    }
    cfg: dict[str, Any] = {
        '$schema': 'https://opencode.ai/config.json',
        'provider': {'logfire-gateway': provider_config},
    }
    if model is not None:
        cfg['model'] = f'logfire-gateway/{model}'
        provider_config['models'] = {model: {}}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2))
    return {'OPENCODE_CONFIG': str(config_path)}


def _configure_claude_mcp(mcp_url: str, console: Console, update: bool) -> None:
    output = subprocess.check_output(['claude', 'mcp', 'list']).decode('utf-8')
    already_configured = bool(re.search(r'(?m)^logfire[\s:]', output))

    if already_configured and not update:
        return

    if already_configured:
        subprocess.check_output(['claude', 'mcp', 'remove', 'logfire'])

    subprocess.check_output(['claude', 'mcp', 'add', '--transport', 'http', 'logfire', mcp_url])
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} Claude.', style='green')


def _configure_codex_mcp(mcp_url: str, console: Console, update: bool) -> None:
    codex_home = Path(os.getenv('CODEX_HOME', Path.home() / '.codex'))
    codex_config = codex_home / 'config.toml'
    if not codex_config.exists():
        console.print('Codex config file not found. Install `codex`, or remove the `--codex` flag.')
        raise SystemExit(1)

    try:
        codex_config_data = read_toml_file(codex_config)
    except ValueError:
        console.print(f'Failed to parse {codex_config} as TOML. Please fix the file or update it manually.')
        raise SystemExit(1) from None
    already_configured = 'logfire' in codex_config_data.get('mcp_servers', {})

    if already_configured and not update:
        return

    mcp_server_toml = LOGFIRE_MCP_TOML.format(url=mcp_url)
    codex_config_content = codex_config.read_text()

    if already_configured:
        new_content = re.sub(
            r'\n?\[mcp_servers\.logfire\].*?(?=\n\[|\Z)',
            mcp_server_toml,
            codex_config_content,
            count=1,
            flags=re.DOTALL,
        )
        codex_config.write_text(new_content)
        console.print('Logfire MCP server updated in Codex.', style='green')
    else:
        codex_config.write_text(codex_config_content + mcp_server_toml)
        console.print('Logfire MCP server added to Codex.', style='green')


def _git_root_or_cwd() -> Path:
    """The repository root the agent will treat as the project, falling back to the cwd."""
    try:
        output = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()
    return Path(output.decode('utf-8').strip())


def _write_repo_config(path: Path, content: str, root_dir: Path, console: Console) -> None:
    """Write a configuration file inside the checkout, refusing to follow a symlink out of it.

    A repository can ship one of these paths, or a parent of it, as a symlink to any file the
    user can write. A plain write would follow that link and overwrite the target with our
    configuration, so both the location and the final write are checked.
    """
    resolved_parent = path.parent.resolve()
    if not resolved_parent.is_relative_to(root_dir.resolve()):
        console.print(f'{path} resolves outside {root_dir}. Refusing to write through it.')
        raise SystemExit(1)
    try:
        # The directory is opened by its already-resolved path, so no link is followed to
        # reach it, and the file is then opened relative to that descriptor. O_NOFOLLOW
        # rejects the final component if it is a link, including a dangling one.
        dir_fd = os.open(resolved_parent, os.O_RDONLY)
        try:
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        console.print(f'{path} is a symbolic link or could not be opened. Refusing to write through it.')
        raise SystemExit(1) from None
    with os.fdopen(fd, 'w') as config_file:
        config_file.write(content)


def _configure_opencode_mcp(mcp_url: str, console: Console, update: bool) -> None:
    root_dir = _git_root_or_cwd()

    opencode_config = root_dir / 'opencode.jsonc'

    # Deliberately not `touch()`ed first: that follows a dangling symlink and creates its
    # target, which is exactly the write outside the checkout that `_write_repo_config`
    # exists to prevent. The file is created by the write itself when it is missing.
    try:
        opencode_config_content = opencode_config.read_text() if opencode_config.is_file() else ''
    except UnicodeDecodeError:
        console.print(f'Failed to read {opencode_config} as text. Please fix the file or update it manually.')
        raise SystemExit(1) from None
    if opencode_config_content.strip():
        try:
            opencode_config_json: dict[str, Any] = json.loads(opencode_config_content)
        except json.JSONDecodeError:
            console.print(
                f'Failed to parse {opencode_config} as JSON. '
                'If it contains JSONC syntax (comments or trailing commas), please update it manually.'
            )
            raise SystemExit(1) from None
    else:
        opencode_config_json = {}
    already_configured = 'logfire-mcp' in opencode_config_json.get('mcp', {})

    if already_configured and not update:
        return

    opencode_config_json.setdefault('mcp', {})['logfire-mcp'] = opencode_mcp_json(mcp_url)
    _write_repo_config(opencode_config, json.dumps(opencode_config_json, indent=2), root_dir, console)
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} OpenCode.', style='green')


def opencode_mcp_json(url: str) -> dict[str, Any]:
    # No `oauth` key: OpenCode detects the requirement on its first connection. Note that an
    # explicit `oauth: false` is not the way to describe a key-authenticated server here, it
    # selects a transport this server answers with a 405.
    return {
        'type': 'remote',
        'url': url,
    }


# Pi has no built-in MCP support: its docs state that it "intentionally does not include built-in
# MCP", and there is no `pi mcp` command. MCP reaches Pi only through the third-party
# `pi-mcp-adapter` package, which reads `mcpServers` from `.pi/mcp.json` among other paths.
PI_MCP_ADAPTER_PACKAGE = 'pi-mcp-adapter'


def _pi_adapter_installed(root_dir: Path) -> bool:
    """Whether `pi-mcp-adapter` is listed in Pi's project-local or global settings."""
    agent_dir = Path(os.getenv('PI_CODING_AGENT_DIR', Path.home() / '.pi' / 'agent'))
    for settings_path in (root_dir / '.pi' / 'settings.json', agent_dir / 'settings.json'):
        try:
            settings: object = json.loads(settings_path.read_text())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        # Someone else's settings file is not ours to validate: an unexpected shape means we
        # cannot tell whether the adapter is installed, which is the same answer as absent.
        if not isinstance(settings, dict):
            continue
        packages = cast('dict[str, Any]', settings).get('packages', [])
        if not isinstance(packages, list):
            continue
        for package in cast('list[str | dict[str, Any]]', packages):
            # Entries are either a source string or a `{'source': ...}` object.
            source = package.get('source', '') if isinstance(package, dict) else package
            if isinstance(source, str) and PI_MCP_ADAPTER_PACKAGE in source:
                return True
    return False


def _configure_pi_mcp(mcp_url: str, console: Console, update: bool) -> None:
    root_dir = _git_root_or_cwd()
    pi_config = root_dir / '.pi' / 'mcp.json'

    def invalid(detail: str) -> NoReturn:
        console.print(f'{pi_config} {detail}. Please fix the file or update it manually.')
        raise SystemExit(1)

    pi_config_json: dict[str, Any] = {}
    if pi_config.exists():
        try:
            loaded: object = json.loads(pi_config.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            invalid('is not valid JSON')
        if not isinstance(loaded, dict):
            invalid('does not contain a JSON object')
        pi_config_json = cast('dict[str, Any]', loaded)

    servers = pi_config_json.setdefault('mcpServers', {})
    if not isinstance(servers, dict):
        invalid('has an "mcpServers" value that is not a JSON object')
    servers = cast('dict[str, Any]', servers)
    already_configured = 'logfire' in servers

    # The warning is reported even when nothing is written, since a configuration Pi cannot
    # read is exactly the case where the reader most needs to hear about the adapter.
    def warn_if_adapter_missing() -> None:
        if not _pi_adapter_installed(root_dir):
            console.print(
                'Pi has no built-in MCP support, so this configuration is only read once the '
                f'community-maintained `{PI_MCP_ADAPTER_PACKAGE}` package is installed:\n'
                f'    pi install npm:{PI_MCP_ADAPTER_PACKAGE}',
                style='yellow',
            )

    if already_configured and not update:
        warn_if_adapter_missing()
        return

    servers['logfire'] = pi_mcp_json(mcp_url)
    pi_config.parent.mkdir(parents=True, exist_ok=True)
    _write_repo_config(pi_config, json.dumps(pi_config_json, indent=2), root_dir, console)
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} Pi.', style='green')
    warn_if_adapter_missing()


def pi_mcp_json(url: str) -> dict[str, Any]:
    # `auth` and `protocolVersion` match how `pi-mcp-adapter` ships its own OAuth-authenticated
    # remote servers; the hosted Logfire MCP server authenticates through the browser too.
    return {
        'url': url,
        'auth': 'oauth',
        'protocolVersion': 'auto',
    }


AI_TOOL_INTEGRATIONS: dict[str, AiToolIntegration] = {
    'claude': AiToolIntegration(
        name='claude',
        display_name='Claude Code',
        binary='claude',
        env={
            'ANTHROPIC_BASE_URL': '{anthropic}',
            'ANTHROPIC_AUTH_TOKEN': '{local_token}',
            'CLAUDE_CODE_USE_BEDROCK': '',
        },
        model_env={'ANTHROPIC_MODEL': '{model}'},
        configure_mcp=_configure_claude_mcp,
        description='Claude Code',
    ),
    'codex': AiToolIntegration(
        name='codex',
        display_name='OpenAI Codex',
        binary='codex',
        env={'OPENAI_BASE_URL': '{openai_v1}', 'OPENAI_API_KEY': '{local_token}'},
        model_env={'OPENAI_MODEL': '{model}'},
        configure_mcp=_configure_codex_mcp,
        description='OpenAI Codex CLI',
    ),
    'opencode': AiToolIntegration(
        name='opencode',
        display_name='OpenCode',
        binary='opencode',
        env={'OPENCODE_PROVIDER': 'logfire-gateway'},
        setup=_opencode_gateway_setup,
        configure_mcp=_configure_opencode_mcp,
        description='OpenCode',
    ),
    # No `env`: Pi configures a gateway base URL through `models.json` in its agent directory, and
    # the only override for that directory (`PI_CODING_AGENT_DIR`) also relocates credentials,
    # settings, and skills, so pointing it at the gateway's temporary working directory would hand
    # the user a blank-slate Pi.
    'pi': AiToolIntegration(
        name='pi',
        display_name='Pi',
        binary='pi',
        configure_mcp=_configure_pi_mcp,
        description='Pi coding agent',
    ),
}
