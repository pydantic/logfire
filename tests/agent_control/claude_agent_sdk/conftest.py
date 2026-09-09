# pyright: reportPrivateUsage=false
"""Fixtures for the adapter tests, and the two ways to see what options actually do.

The offline tests here never spawn the `claude` CLI or reach the network. Instead both halves of what
options mean are read offline: the arguments the SDK would spawn the CLI with, and the tool
definitions the SDK would serve an in-process MCP server's tools as. The Logfire project, the reset
of once-per-process state, and the credential scrubbing all come from the conftests above this one.

`test_live.py` is the exception: it drives the real CLI through a recorded cassette, and registers
the flag that records one.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any, cast

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
from claude_agent_sdk.types import McpSdkServerConfig

from logfire.agent_control import _control
from logfire.variables import LabeledValue, Rollout, VariableConfig
from logfire.variables.local import LocalVariableProvider


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--record-agent-control-cassettes',
        action='store_true',
        default=False,
        help='Record the Agent Control cassettes in this directory against a real `claude` CLI.',
    )


@pytest.fixture(autouse=True)
def _join_baseline_publishes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Wait for the baseline publishers a test started before the next test begins.

    `agent_control()` publishes the baseline on a daemon thread and hands the caller options rather
    than the thread, which is the right shape for an agent and the wrong one for a test suite: the
    thread builds pydantic models, and the suite asserts between tests that no pydantic plugin load
    is in flight.
    """
    spawned: list[threading.Thread] = []
    spawn = _control._spawn_baseline_publish

    def record(*args: Any, **kwargs: Any) -> threading.Thread:
        thread = spawn(*args, **kwargs)
        spawned.append(thread)
        return thread

    monkeypatch.setattr(_control, '_spawn_baseline_publish', record)
    yield
    for thread in spawned:
        thread.join(timeout=10)


def publish(provider: LocalVariableProvider, name: str, value: Any, *, label: str = 'production') -> VariableConfig:
    """Put `value` in the project under one label, the shape a project has once someone saved in the UI.

    Publishing again bumps that label's version and leaves the other labels alone, so a test can
    publish, change, and withdraw the way someone editing in Logfire does.
    """
    existing = provider.get_variable_config(name)
    labels = dict(existing.labels) if existing is not None else {}
    published = labels.get(label)
    version = 1 if not isinstance(published, LabeledValue) else published.version + 1
    labels[label] = LabeledValue(version=version, serialized_value=json.dumps(value))
    config = VariableConfig(name=name, labels=labels, rollout=Rollout(labels={label: 1.0}), overrides=[])
    return provider.create_variable(config) if existing is None else provider.update_variable(name, config)


def withdraw(provider: LocalVariableProvider, name: str) -> None:
    """Take the whole config back out of the project, the way removing it in Logfire does."""
    provider.delete_variable(name)


def cli_args(options: ClaudeAgentOptions) -> list[str]:
    """The command line the SDK would spawn the `claude` CLI with for these options.

    This reaches into the SDK's transport, which is the only place the mapping from options to CLI
    arguments exists -- and that mapping is the whole of what an applied config *does* here, since the
    prompt, the model, and the effort are all decided inside the process those arguments start. The
    CLI path is stubbed so nothing is looked up or spawned.
    """
    transport = SubprocessCLITransport(prompt='hi', options=options)
    transport._cli_path = '/stub/claude'
    return transport._build_command()


def cli_arg(options: ClaudeAgentOptions, flag: str) -> str | None:
    """The value the CLI would be given for one flag, or `None` when the flag is absent."""
    args = cli_args(options)
    return args[args.index(flag) + 1] if flag in args else None


async def _bridged(config: McpSdkServerConfig, request: dict[str, Any]) -> dict[str, Any]:
    """Run one MCP request against an in-process server the way the SDK serves it to the CLI."""
    bridge = SdkMcpBridge(config['name'], config['instance'])
    await bridge.handle(
        {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '0'},
            },
        }
    )
    await bridge.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    response = await bridge.handle({'jsonrpc': '2.0', 'id': 2, **request})
    await bridge.aclose()
    assert response is not None
    return cast(dict[str, Any], response['result'])


def wire_tools(options: ClaudeAgentOptions, server: str) -> list[dict[str, Any]]:
    """The tool definitions the model is shown for one in-process server."""
    servers = cast(dict[str, McpSdkServerConfig], options.mcp_servers)
    result = anyio.run(_bridged, servers[server], {'method': 'tools/list'})
    return cast(list[dict[str, Any]], result['tools'])


def call_tool(options: ClaudeAgentOptions, server: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one in-process tool by the name the model would call it, and return the MCP result."""
    servers = cast(dict[str, McpSdkServerConfig], options.mcp_servers)
    return anyio.run(
        _bridged, servers[server], {'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}
    )
