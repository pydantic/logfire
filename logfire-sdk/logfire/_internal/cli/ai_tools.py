from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    env: dict[str, str]
    model_env: dict[str, str] = field(default_factory=dict[str, str])
    setup: Callable[[str, str | None, Path, str], dict[str, str]] | None = None
    configure_mcp: Callable[[str, Console, bool], None] | None = None
    description: str = ''
    notice: str = ''

    def binary_path(self) -> str | None:
        return shutil.which(self.binary)

    def build_gateway_env(
        self, *, proxy_base: str, model: str | None, workdir: Path, local_token: str
    ) -> dict[str, str]:
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


def _configure_opencode_mcp(mcp_url: str, console: Console, update: bool) -> None:
    try:
        output = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
    except (subprocess.CalledProcessError, FileNotFoundError):
        root_dir = Path.cwd()
    else:
        root_dir = Path(output.decode('utf-8').strip())

    opencode_config = root_dir / 'opencode.jsonc'
    opencode_config.touch()

    opencode_config_content = opencode_config.read_text()
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
    opencode_config.write_text(json.dumps(opencode_config_json, indent=2))
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} OpenCode.', style='green')


def opencode_mcp_json(url: str) -> dict[str, Any]:
    return {
        'type': 'remote',
        'url': url,
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
}
