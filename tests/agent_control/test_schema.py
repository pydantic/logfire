"""The stored JSON schema is one half of a contract, so it is pinned rather than merely exercised."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from logfire.agent_control import (
    AGENT_CONFIG_JSON_SCHEMA,
    SCHEMA_SHA256,
    AgentConfig,
    AgentConfigSettings,
    InstructionBlock,
    ToolDefinitionOverride,
)

LOCKSTEP = (
    'AGENT_CONFIG_JSON_SCHEMA is one half of a contract with the Logfire UI and with every other '
    'Agent Control SDK: update the TypeScript package and '
    'src/services/logfire-frontend/src/app/project/managed-agents/agent-config.ts in the Logfire '
    'platform repo in lockstep, or a UI-created variable and an SDK-created one will store different '
    'schemas for the same agent.'
)

CANONICAL_SCHEMA_SHA256 = 'e4c38488d6c46440dbf31939291e13fcd56814c1305bc9012cd2158733b0bbad'

INSTRUCTIONS_SCHEMA: dict[str, Any] = AGENT_CONFIG_JSON_SCHEMA['properties']['instructions']
SETTINGS_SCHEMA: dict[str, Any] = AGENT_CONFIG_JSON_SCHEMA['properties']['settings']
TOOL_OVERRIDE_SCHEMA: dict[str, Any] = AGENT_CONFIG_JSON_SCHEMA['properties']['tool_definitions']['items']

# The object branch of an `instructions` entry, the other branch being a bare string.
INSTRUCTION_BLOCK_SCHEMA: dict[str, Any] = next(
    option for option in INSTRUCTIONS_SCHEMA['anyOf'][1]['items']['anyOf'] if option['type'] == 'object'
)


def subschemas(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Every object schema reachable from `schema`, itself included."""
    yield schema
    children: list[Any] = [
        *cast(dict[str, Any], schema.get('properties', {})).values(),
        schema.get('items'),
        schema.get('additionalProperties'),
        *cast(list[Any], schema.get('anyOf', [])),
    ]
    for child in children:
        if isinstance(child, dict):
            yield from subschemas(cast(dict[str, Any], child))


def test_schema_matches_the_digest_every_copy_pins() -> None:
    assert SCHEMA_SHA256 == CANONICAL_SCHEMA_SHA256, LOCKSTEP


def test_every_model_field_is_described() -> None:
    assert set(AgentConfig.model_fields) == set(AGENT_CONFIG_JSON_SCHEMA['properties']), LOCKSTEP
    assert set(AgentConfigSettings.model_fields) == set(SETTINGS_SCHEMA['properties']), LOCKSTEP
    assert set(ToolDefinitionOverride.model_fields) == set(TOOL_OVERRIDE_SCHEMA['properties']), LOCKSTEP
    assert set(InstructionBlock.model_fields) == set(INSTRUCTION_BLOCK_SCHEMA['properties']), LOCKSTEP


def test_schema_is_permissive_at_every_level() -> None:
    # A closed schema anywhere would make the Logfire backend reject a write that `AgentConfig` is
    # built to tolerate, so the forward-compatibility contract lives in the stored schema too.
    for subschema in subschemas(AGENT_CONFIG_JSON_SCHEMA):
        assert subschema.get('additionalProperties') is not False, LOCKSTEP
        assert 'enum' not in subschema, LOCKSTEP
