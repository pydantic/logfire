"""What a published value does to a request, which is the whole of what an adapter delegates."""

from __future__ import annotations

from typing import Any

import pytest

from logfire.agent_control import (
    MAX_MODEL_FACING_TEXT_LENGTH,
    AgentConfig,
    AppliedInstructions,
    AppliedTools,
    Block,
    InstructionBlock,
    ToolDef,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
)

AGENT = Block('You are a checkout assistant.', id='agent')
REFUNDS = Block('Always confirm the order total.', id='agent:refunds')
TODAY = Block('Today is 2026-09-09.', id='agent:today', dynamic=True)

WEATHER = ToolDef(
    name='get_weather',
    description='Get the current weather for a city.',
    parameters_json_schema={
        'type': 'object',
        'properties': {'city': {'type': 'string', 'description': 'City to look up.'}},
        'required': ['city'],
    },
    toolset='<agent>',
)
SEARCH = ToolDef(name='search', description='Search the CRM.', toolset='crm')


def config(**sections: Any) -> AgentConfig:
    return AgentConfig.model_validate(sections)


def test_nothing_published_leaves_every_block_alone() -> None:
    blocks = [AGENT, TODAY]
    assert apply_instructions(blocks, AgentConfig()) == AppliedInstructions(blocks=blocks, unapplied=())


def test_an_id_replaces_that_blocks_text_and_leaves_its_position_and_flag() -> None:
    applied = apply_instructions(
        [AGENT, REFUNDS, TODAY], config(instructions=[{'id': 'agent:refunds', 'instructions': 'Confirm the total.'}])
    )
    assert applied.blocks == [AGENT, Block('Confirm the total.', id='agent:refunds'), TODAY]


def test_an_id_with_no_text_drops_the_block() -> None:
    assert apply_instructions([AGENT, REFUNDS], config(instructions=[{'id': 'agent:refunds'}])).blocks == [AGENT]


def test_an_added_block_lands_before_the_first_dynamic_one() -> None:
    # The added text has to sit inside the prefix a provider can cache, which is everything before
    # the first block the agent recomputes per request.
    applied = apply_instructions([AGENT, TODAY], config(instructions=['Escalate anything over $500.']))
    assert applied.blocks == [AGENT, Block('Escalate anything over $500.'), TODAY]


def test_the_short_form_is_one_added_block() -> None:
    applied = apply_instructions([AGENT, TODAY], config(instructions='Escalate anything over $500.'))
    assert applied.blocks == [AGENT, Block('Escalate anything over $500.'), TODAY]


def test_added_blocks_are_appended_in_order_when_nothing_is_dynamic() -> None:
    applied = apply_instructions([AGENT], config(instructions=['First.', {'instructions': 'Second.'}]))
    assert applied.blocks == [AGENT, Block('First.'), Block('Second.')]


def test_a_block_with_no_id_cannot_be_addressed_and_passes_through() -> None:
    anonymous = Block('Assembled by a callable nobody named.')
    applied = apply_instructions([anonymous], config(instructions=['Added.']))
    assert applied.blocks == [anonymous, Block('Added.')]


def test_a_dynamic_block_is_not_addressable() -> None:
    with pytest.warns(UserWarning, match="addresses instruction block 'agent:today', which the agent recomputes"):
        applied = apply_instructions([AGENT, TODAY], config(instructions=[{'id': 'agent:today', 'instructions': 'x'}]))
    assert applied.blocks == [AGENT, TODAY]
    assert [(e.reason, e.instruction_id) for e in applied.unapplied] == [('dynamic-id', 'agent:today')]


def test_an_id_this_request_does_not_assemble_is_reported_once() -> None:
    with pytest.warns(UserWarning, match="addresses instruction block 'toolset:crm', which this request does not"):
        applied = apply_instructions([AGENT], config(instructions=[{'id': 'toolset:crm', 'instructions': 'x'}]))
    assert applied.blocks == [AGENT]
    assert [(e.reason, e.instruction_id) for e in applied.unapplied] == [('unknown-id', 'toolset:crm')]


def test_an_unmatched_entry_can_be_ignored_or_raised() -> None:
    published = config(instructions=[{'id': 'toolset:crm', 'instructions': 'x'}])
    assert apply_instructions([AGENT], published, on_unmatched='ignore').blocks == [AGENT]
    with pytest.raises(ValueError, match="addresses instruction block 'toolset:crm'"):
        apply_instructions([AGENT], published, on_unmatched='error')


def test_two_entries_naming_one_id_keep_the_first() -> None:
    with pytest.warns(UserWarning, match="names instruction id 'agent' more than once"):
        applied = apply_instructions(
            [AGENT],
            config(instructions=[{'id': 'agent', 'instructions': 'First.'}, {'id': 'agent', 'instructions': 'Last.'}]),
        )
    assert applied.blocks == [Block('First.', id='agent')]


def test_a_description_override_leaves_the_rest_of_the_schema_alone() -> None:
    patched = ToolDef(
        name='get_weather',
        description='Look up the weather.',
        parameters_json_schema={
            'type': 'object',
            'properties': {'city': {'type': 'string', 'description': "City name, e.g. 'London'"}},
            'required': ['city'],
        },
        toolset='<agent>',
    )
    applied = apply_tool_definitions(
        [WEATHER],
        config(
            tool_definitions=[
                {
                    'name': 'get_weather',
                    'description': 'Look up the weather.',
                    'parameters': {'city': {'description': "City name, e.g. 'London'"}},
                }
            ]
        ),
    )
    assert applied == AppliedTools(
        tools=[patched],
        routes={'get_weather': 'get_weather'},
        forward={('<agent>', 'get_weather'): 'get_weather'},
        reverse={('<agent>', 'get_weather'): 'get_weather'},
        unapplied=[],
    )


def test_a_patch_on_a_parameter_the_tool_does_not_have_is_reported() -> None:
    # It used to be silent, which from the Logfire UI looked exactly like a patch that applied.
    published = config(tool_definitions=[{'name': 'get_weather', 'parameters': {'unknown': {'description': 'x'}}}])
    with pytest.warns(UserWarning, match="patches parameter 'unknown' of tool 'get_weather' from toolset '<agent>'"):
        applied = apply_tool_definitions([WEATHER], published)
    assert applied.tools == [WEATHER]
    assert [(e.reason, e.tool, e.parameter, e.toolset) for e in applied.unapplied] == [
        ('unknown-parameter', 'get_weather', 'unknown', '<agent>')
    ]
    with pytest.raises(ValueError, match="patches parameter 'unknown'"):
        apply_tool_definitions([WEATHER], published, on_unmatched='error')


def test_a_parameter_whose_schema_is_not_an_object_cannot_be_patched() -> None:
    tool = ToolDef(name='odd', parameters_json_schema={'type': 'object', 'properties': {'flag': True}})
    published = config(tool_definitions=[{'name': 'odd', 'parameters': {'flag': {'description': 'x'}}}])
    with pytest.warns(UserWarning, match='describes that parameter with no schema object'):
        applied = apply_tool_definitions([tool], published)
    assert applied.tools == [tool]
    assert [e.reason for e in applied.unapplied] == ['no-patchable-schema']


def test_an_override_that_changes_nothing_returns_the_definition_it_was_given() -> None:
    applied = apply_tool_definitions(
        [WEATHER],
        config(
            tool_definitions=[
                {
                    'name': 'get_weather',
                    'new_name': 'get_weather',
                    'description': 'Get the current weather for a city.',
                    'parameters': {'city': {'description': None}},
                }
            ]
        ),
    )
    assert applied.tools[0] is WEATHER


def test_a_tool_with_no_patchable_schema_reports_every_parameter_patch() -> None:
    tool = ToolDef(name='ping', parameters_json_schema={'type': 'object'})
    with pytest.warns(UserWarning, match="patches parameter 'city' of tool 'ping', which has no top-level parameters"):
        applied = apply_tool_definitions(
            [tool], config(tool_definitions=[{'name': 'ping', 'parameters': {'city': {'description': 'x'}}}])
        )
    assert applied.tools == [tool]
    assert [(e.reason, e.parameter) for e in applied.unapplied] == [('no-patchable-schema', 'city')]


def test_a_rename_is_advertised_and_routed_back_to_the_code_name() -> None:
    applied = apply_tool_definitions(
        [WEATHER, SEARCH], config(tool_definitions=[{'name': 'get_weather', 'new_name': 'lookup_weather'}])
    )
    assert [tool.name for tool in applied.tools] == ['lookup_weather', 'search']
    assert applied.routes == {'lookup_weather': 'get_weather', 'search': 'search'}


def test_a_rename_onto_another_advertised_name_is_dropped_and_the_rest_of_the_patch_applies() -> None:
    published = config(tool_definitions=[{'name': 'get_weather', 'new_name': 'search', 'description': 'Weather.'}])
    with pytest.warns(UserWarning, match="renames 'get_weather' to 'search', which is already advertised"):
        applied = apply_tool_definitions([WEATHER, SEARCH], published)
    assert applied.tools[0] == ToolDef(
        name='get_weather',
        description='Weather.',
        parameters_json_schema=WEATHER.parameters_json_schema,
        toolset='<agent>',
    )
    assert applied.routes == {'get_weather': 'get_weather', 'search': 'search'}
    assert [(e.reason, e.tool) for e in applied.unapplied] == [('rename-collision', 'get_weather')]


def test_a_dropped_rename_obeys_the_policy_like_every_other_decision() -> None:
    # It used to warn unconditionally, so `'ignore'` still warned and `'error'` did not fail.
    published = config(tool_definitions=[{'name': 'get_weather', 'new_name': 'search'}])
    applied = apply_tool_definitions([WEATHER, SEARCH], published, on_unmatched='ignore')
    assert [tool.name for tool in applied.tools] == ['get_weather', 'search']
    with pytest.raises(ValueError, match="renames 'get_weather' to 'search'"):
        apply_tool_definitions([WEATHER, SEARCH], published, on_unmatched='error')


def test_a_rename_onto_a_name_the_adapter_reserved_is_refused() -> None:
    # An OpenAI Agents handoff, or a provider tool the framework adds after this call: outside the
    # editable list, and the core cannot see it unless the adapter says so.
    published = config(tool_definitions=[{'name': 'get_weather', 'new_name': 'transfer_to_billing'}])
    with pytest.warns(UserWarning, match="renames 'get_weather' to 'transfer_to_billing'"):
        applied = apply_tool_definitions([WEATHER], published, reserved={'transfer_to_billing'})
    assert [tool.name for tool in applied.tools] == ['get_weather']


def test_names_collide_per_toolset_when_the_runtime_name_carries_the_toolset() -> None:
    # Claude advertises `mcp__<server>__<tool>`, so two servers may each answer to `lookup`.
    crm = ToolDef(name='search', toolset='crm')
    docs = ToolDef(name='lookup', toolset='docs')
    published = config(tool_definitions=[{'name': 'search', 'toolset': 'crm', 'new_name': 'lookup'}])
    applied = apply_tool_definitions([crm, docs], published, collision_scope='toolset')
    assert [tool.name for tool in applied.tools] == ['lookup', 'lookup']
    assert applied.unapplied == []
    # The flat map cannot tell the two apart, which is exactly why the identity maps exist.
    assert applied.reverse == {('crm', 'lookup'): 'search', ('docs', 'lookup'): 'lookup'}
    assert applied.forward == {('crm', 'search'): 'lookup', ('docs', 'lookup'): 'lookup'}
    assert applied.routes == {'lookup': 'search'}
    # The same rename against one flat namespace is a collision.
    globally = apply_tool_definitions([crm, docs], published, on_unmatched='ignore')
    assert [tool.name for tool in globally.tools] == ['search', 'lookup']


def test_a_rename_onto_a_name_an_earlier_rename_took_is_dropped_too() -> None:
    with pytest.warns(UserWarning, match="renames 'search' to 'lookup', which is already advertised"):
        applied = apply_tool_definitions(
            [WEATHER, SEARCH],
            config(
                tool_definitions=[
                    {'name': 'get_weather', 'new_name': 'lookup'},
                    {'name': 'search', 'new_name': 'lookup'},
                ]
            ),
        )
    assert applied.routes == {'lookup': 'get_weather', 'search': 'search'}


def test_a_toolset_qualified_override_beats_one_that_only_names_the_tool() -> None:
    crm_search = ToolDef(name='search', description='Search the CRM.', toolset='crm')
    docs_search = ToolDef(name='search', description='Search the docs.', toolset='docs')
    applied = apply_tool_definitions(
        [crm_search, docs_search],
        config(
            tool_definitions=[
                {'name': 'search', 'description': 'Search something.'},
                {'name': 'search', 'toolset': 'crm', 'description': 'Search CRM records.'},
            ]
        ),
    )
    # The unqualified entry is outranked where the narrowed one applies, not unmatched: it reached
    # the docs tool, so nothing is reported.
    assert [tool.description for tool in applied.tools] == ['Search CRM records.', 'Search something.']


def test_an_override_that_matches_no_tool_is_reported() -> None:
    published = config(tool_definitions=[{'name': 'search', 'toolset': 'crm'}])
    with pytest.warns(UserWarning, match="patches tool 'search' from toolset 'crm', which no toolset advertises"):
        assert apply_tool_definitions([WEATHER], published).tools == [WEATHER]
    assert apply_tool_definitions([WEATHER], published, on_unmatched='ignore').tools == [WEATHER]
    with pytest.raises(ValueError, match="patches tool 'search' from toolset 'crm'"):
        apply_tool_definitions([WEATHER], published, on_unmatched='error')


def test_two_overrides_naming_one_tool_keep_the_first() -> None:
    with pytest.warns(UserWarning, match="names tool 'get_weather' more than once"):
        applied = apply_tool_definitions(
            [WEATHER],
            config(
                tool_definitions=[
                    {'name': 'get_weather', 'description': 'First.'},
                    {'name': 'get_weather', 'description': 'Last.'},
                ]
            ),
        )
    assert applied.tools[0].description == 'First.'


def test_no_settings_published_is_an_empty_patch() -> None:
    assert apply_settings(AgentConfig()) == {}


def test_only_the_keys_that_were_set_are_in_the_patch() -> None:
    assert apply_settings(config(settings={'temperature': 0.4, 'stop_sequences': ['STOP']})) == {
        'temperature': 0.4,
        'stop_sequences': ['STOP'],
    }


def test_a_key_this_contract_has_no_field_for_is_reported() -> None:
    published = config(settings={'temperature': 0.4, 'service_tier': 'flex'})
    with pytest.warns(UserWarning, match="sets 'service_tier', which this version of the Agent Control contract"):
        assert apply_settings(published) == {'temperature': 0.4}
    with pytest.raises(ValueError, match="sets 'service_tier'"):
        apply_settings(published, on_unmatched='error')


def test_a_key_the_adapter_cannot_lower_is_reported_and_left_out() -> None:
    published = config(settings={'temperature': 0.4, 'top_k': 20})
    with pytest.warns(UserWarning, match="sets 'top_k', which this agent framework has no equivalent for"):
        assert apply_settings(published, supported={'temperature', 'max_tokens'}) == {'temperature': 0.4}
    assert apply_settings(published, supported={'temperature'}, on_unmatched='ignore') == {'temperature': 0.4}


def test_a_config_assembled_in_code_may_hold_bare_strings_in_its_list() -> None:
    # Assignment is not re-validated, so an adapter building a config by hand -- a test, a migration
    # script -- can leave the shorthand in place; a bare entry means the same thing either way.
    published = AgentConfig()
    published.instructions = ['Escalate anything over $500.']
    assert apply_instructions([AGENT], published).blocks == [AGENT, Block('Escalate anything over $500.')]


def test_text_past_the_budget_is_refused_rather_than_truncated() -> None:
    # The budget belongs to the contract rather than to one language's model. Parsing a published
    # value enforces it, and `InstructionBlock` enforces it again on anything validated -- but the
    # apply step is the shared algorithm both cores implement, and in TypeScript, where the parsed
    # shape is a plain interface with no runtime bound, this is where an oversized entry is caught.
    # `model_construct` is the only way to get one past both of Python's checks.
    published = AgentConfig()
    published.instructions = [
        InstructionBlock.model_construct(id='agent', instructions='a' * (MAX_MODEL_FACING_TEXT_LENGTH + 1)),
        InstructionBlock.model_construct(instructions='b' * (MAX_MODEL_FACING_TEXT_LENGTH + 1)),
    ]
    with pytest.warns(UserWarning, match='past the 65536-character limit'):
        applied = apply_instructions([AGENT], published)
    assert applied.blocks == [AGENT]
    assert [(e.reason, e.instruction_id) for e in applied.unapplied] == [
        ('oversized-text', 'agent'),
        ('oversized-text', None),
    ]
    with pytest.raises(ValueError, match='past the 65536-character limit'):
        apply_instructions([AGENT], published, on_unmatched='error')
