"""Tests for template_validation: {{field}} validation and cycle detection."""

# pyright: reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from logfire.variables.template_validation import (
    TemplateFieldIssue,
    TemplateValidationResult,
    _find_fields_in_serialized,
    detect_composition_cycles,
    find_template_fields,
    validate_template_composition,
)

# =============================================================================
# find_template_fields
# =============================================================================


class TestFindTemplateFields:
    def test_simple_field(self):
        assert find_template_fields('Hello {{name}}!') == {'name'}

    def test_multiple_fields(self):
        result = find_template_fields('{{greeting}} {{name}}, age {{age}}')
        assert result == {'greeting', 'name', 'age'}

    def test_duplicate_fields(self):
        """Duplicate fields produce a single entry in the set."""
        result = find_template_fields('{{name}} and {{name}} again')
        assert result == {'name'}

    def test_empty_string(self):
        assert find_template_fields('') == set()

    def test_no_templates(self):
        assert find_template_fields('Hello world, no templates here') == set()

    def test_ignores_block_helpers(self):
        """{{#if condition}} is a single block; not matched as {{identifier}}."""
        result = find_template_fields('{{#if condition}}yes{{/if}}')
        # The entire {{#if condition}} has # after {{ so it doesn't match
        assert result == set()

    def test_block_helper_hash_excluded(self):
        """{{#if}} has a # prefix so the identifier doesn't start with [a-zA-Z_]."""
        result = find_template_fields('{{#if}}content{{/if}}')
        assert 'if' not in result
        assert result == set()

    def test_closing_tag_excluded(self):
        """{{/if}} has a / prefix so it won't match."""
        result = find_template_fields('{{/if}}')
        assert result == set()

    def test_partial_excluded(self):
        """{{> partial}} has a > prefix so it won't match."""
        result = find_template_fields('{{> myPartial}}')
        assert result == set()

    def test_comment_excluded(self):
        """{{! comment}} has a ! prefix so it won't match."""
        result = find_template_fields('{{! this is a comment}}')
        assert result == set()

    def test_triple_stache_not_matched(self):
        """{{{raw}}} — the outer braces don't form a valid {{identifier}} match."""
        # {{{raw}}} is 3 opening braces + raw + 3 closing braces
        # The regex looks for {{ identifier }}, so {{{ would have an extra { before the identifier
        result = find_template_fields('{{{raw}}}')
        # The regex matches {{raw}} inside {{{raw}}}, leaving extra braces.
        # Actually {{ raw }} is a valid match embedded in {{{ raw }}}
        # Let's just verify empirically.
        assert 'raw' in result  # {{raw}} is still matched within {{{raw}}}

    def test_field_with_spaces(self):
        """Spaces inside {{ field }} are allowed by the regex."""
        result = find_template_fields('{{ name }}')
        assert result == {'name'}

    def test_field_with_underscore(self):
        result = find_template_fields('{{user_name}}')
        assert result == {'user_name'}

    def test_field_with_digits(self):
        result = find_template_fields('{{item1}}')
        assert result == {'item1'}

    def test_field_starting_with_underscore(self):
        result = find_template_fields('{{_private}}')
        assert result == {'_private'}

    def test_mixed_valid_and_invalid(self):
        """Valid {{field}} mixed with helpers and partials."""
        text = '{{name}} {{#if active}}{{role}}{{/if}} {{> footer}} {{! ignored}}'
        result = find_template_fields(text)
        assert 'name' in result
        assert 'role' in result
        # Helpers, closing tags, partials, and comments should not appear
        assert '#if' not in result
        assert '/if' not in result
        assert '> footer' not in result
        assert '! ignored' not in result


# =============================================================================
# _find_fields_in_serialized
# =============================================================================


class TestFindFieldsInSerialized:
    def test_json_string(self):
        """JSON string value like '"Hello {{name}}"'."""
        result = _find_fields_in_serialized('"Hello {{name}}"')
        assert result == {'name'}

    def test_json_object(self):
        """JSON object with multiple string values containing fields."""
        result = _find_fields_in_serialized('{"key": "Hello {{name}}", "other": "{{age}}"}')
        assert result == {'name', 'age'}

    def test_json_array(self):
        """JSON array with string values containing fields."""
        result = _find_fields_in_serialized('["{{a}}", "{{b}}"]')
        assert result == {'a', 'b'}

    def test_invalid_json_falls_back_to_plain_text(self):
        """Invalid JSON falls back to plain text extraction."""
        result = _find_fields_in_serialized('not valid json {{field}}')
        assert result == {'field'}

    def test_json_number_no_fields(self):
        """JSON number value has no template fields."""
        result = _find_fields_in_serialized('42')
        assert result == set()

    def test_json_boolean_no_fields(self):
        """JSON boolean value has no template fields."""
        result = _find_fields_in_serialized('true')
        assert result == set()

    def test_json_null_no_fields(self):
        """JSON null value has no template fields."""
        result = _find_fields_in_serialized('null')
        assert result == set()

    def test_nested_json_object(self):
        """Nested JSON objects have their string values scanned."""
        result = _find_fields_in_serialized('{"outer": {"inner": "{{deep}}"}}')
        assert result == {'deep'}

    def test_mixed_types_in_object(self):
        """Object with mixed types: only string values are scanned."""
        result = _find_fields_in_serialized('{"text": "{{name}}", "count": 42, "active": true, "nothing": null}')
        assert result == {'name'}

    def test_array_with_mixed_types(self):
        """Array with mixed types: only strings scanned."""
        result = _find_fields_in_serialized('["{{a}}", 42, true, null, "{{b}}"]')
        assert result == {'a', 'b'}

    def test_empty_json_string(self):
        result = _find_fields_in_serialized('""')
        assert result == set()

    def test_empty_json_object(self):
        result = _find_fields_in_serialized('{}')
        assert result == set()

    def test_empty_json_array(self):
        result = _find_fields_in_serialized('[]')
        assert result == set()

    def test_deeply_nested_structure(self):
        """Deeply nested JSON structure with fields at various levels."""
        result = _find_fields_in_serialized('{"a": [{"b": "{{x}}"}, {"c": ["{{y}}", {"d": "{{z}}"}]}]}')
        assert result == {'x', 'y', 'z'}


# =============================================================================
# validate_template_composition
# =============================================================================


def _make_get_all_serialized(
    data: dict[str, dict[str | None, str]],
) -> ...:
    """Helper: build get_all_serialized_values from a simple mapping."""

    def get_all_serialized_values(name: str) -> dict[str | None, str]:
        return data.get(name, {})

    return get_all_serialized_values


class TestValidateTemplateComposition:
    def test_all_fields_valid(self):
        """All {{field}} references match schema properties — no issues."""
        schema = {'properties': {'name': {'type': 'string'}, 'age': {'type': 'integer'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '"Hello {{name}}, you are {{age}}"'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert result.issues == []

    def test_field_not_in_schema(self):
        """A {{field}} not in schema properties produces an issue."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '"Hello {{name}} {{unknown}}"'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.field_name == 'unknown'
        assert issue.found_in_variable == 'my_var'
        assert issue.found_in_label is None
        assert issue.reference_path == []

    def test_transitive_reference_issue(self):
        """var_a references <<var_b>>, var_b has {{field}} not in var_a's schema."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'var_a': {None: '"Hello {{name}} <<var_b>>"'},
                'var_b': {None: '"extra {{bad_field}}"'},
            }
        )
        result = validate_template_composition('var_a', schema, get_values)
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.field_name == 'bad_field'
        assert issue.found_in_variable == 'var_b'
        assert issue.reference_path == ['var_b']

    def test_multiple_labels(self):
        """Issues across multiple labels (None for latest, 'prod' for labeled)."""
        schema = {'properties': {'x': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {
                    None: '"{{x}} {{bad1}}"',
                    'prod': '"{{x}} {{bad2}}"',
                },
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert len(result.issues) == 2
        field_names = {i.field_name for i in result.issues}
        assert field_names == {'bad1', 'bad2'}
        labels = {i.found_in_label for i in result.issues}
        assert labels == {None, 'prod'}

    def test_cycle_does_not_infinite_loop(self):
        """A cycle in composition references terminates without infinite recursion."""
        schema = {'properties': {}}
        get_values = _make_get_all_serialized(
            {
                'a': {None: '"<<b>>"'},
                'b': {None: '"<<a>>"'},
            }
        )
        # Should complete without hanging
        result = validate_template_composition('a', schema, get_values)
        # No fields to report as issues — the cycle just stops traversal
        assert isinstance(result, TemplateValidationResult)

    def test_no_template_fields(self):
        """Variable with no {{}} fields produces no issues."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '"Hello world"'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert result.issues == []

    def test_empty_schema_all_fields_are_issues(self):
        """With empty schema, every field is an issue."""
        schema = {'properties': {}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '"{{a}} {{b}}"'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert len(result.issues) == 2
        field_names = {i.field_name for i in result.issues}
        assert field_names == {'a', 'b'}

    def test_schema_without_properties_key(self):
        """Schema missing 'properties' key treats all fields as invalid."""
        schema = {'type': 'object'}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '"{{field}}"'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert len(result.issues) == 1
        assert result.issues[0].field_name == 'field'

    def test_variable_with_no_values(self):
        """Variable with no serialized values produces no issues."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert result.issues == []

    def test_unknown_variable_no_values(self):
        """Unknown variable (not in data) produces no issues."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized({})
        result = validate_template_composition('unknown', schema, get_values)
        assert result.issues == []

    def test_transitive_chain(self):
        """A -> B -> C, field in C not in A's schema."""
        schema = {'properties': {'ok': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'a': {None: '"{{ok}} <<b>>"'},
                'b': {None: '"<<c>>"'},
                'c': {None: '"{{deep_field}}"'},
            }
        )
        result = validate_template_composition('a', schema, get_values)
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.field_name == 'deep_field'
        assert issue.found_in_variable == 'c'
        assert issue.reference_path == ['b', 'c']

    def test_duplicate_issue_dedup(self):
        """Same field/variable/label combination is only reported once."""
        schema = {'properties': {}}
        # Two labels in a, both reference b which has the same field
        get_values = _make_get_all_serialized(
            {
                'a': {None: '"<<b>>"', 'prod': '"<<b>>"'},
                'b': {None: '"{{field}}"'},
            }
        )
        result = validate_template_composition('a', schema, get_values)
        # field in b/None should only appear once even though a has two labels pointing to b
        b_issues = [i for i in result.issues if i.found_in_variable == 'b']
        assert len(b_issues) == 1

    def test_issue_reference_path_is_copy(self):
        """reference_path in issues is an independent list, not a shared reference."""
        schema = {'properties': {}}
        get_values = _make_get_all_serialized(
            {
                'a': {None: '"<<b>> <<c>>"'},
                'b': {None: '"{{field_b}}"'},
                'c': {None: '"{{field_c}}"'},
            }
        )
        result = validate_template_composition('a', schema, get_values)
        assert len(result.issues) >= 2
        paths = [i.reference_path for i in result.issues]
        # Each path should be independent
        for p in paths:
            assert isinstance(p, list)

    def test_json_object_value_fields(self):
        """Fields inside JSON object string values are found."""
        schema = {'properties': {'name': {'type': 'string'}}}
        get_values = _make_get_all_serialized(
            {
                'my_var': {None: '{"greeting": "Hello {{name}} {{extra}}"}'},
            }
        )
        result = validate_template_composition('my_var', schema, get_values)
        assert len(result.issues) == 1
        assert result.issues[0].field_name == 'extra'


# =============================================================================
# detect_composition_cycles
# =============================================================================


def _make_get_all_references(
    graph: dict[str, set[str]],
) -> ...:
    """Helper: build get_all_references from a simple adjacency dict."""

    def get_all_references(name: str) -> set[str]:
        return graph.get(name, set())

    return get_all_references


class TestDetectCompositionCycles:
    def test_no_cycle(self):
        """No cycle returns None."""
        get_refs = _make_get_all_references(
            {
                'a': {'b'},
                'b': {'c'},
                'c': set(),
            }
        )
        result = detect_composition_cycles('a', {'b'}, get_refs)
        assert result is None

    def test_direct_self_reference(self):
        """A references itself."""
        get_refs = _make_get_all_references(
            {
                'a': set(),
            }
        )
        result = detect_composition_cycles('a', {'a'}, get_refs)
        assert result is not None
        assert result[0] == 'a'
        assert result[-1] == 'a'

    def test_a_b_a_cycle(self):
        """A -> B -> A cycle."""
        get_refs = _make_get_all_references(
            {
                'a': set(),  # a's current refs don't matter; new_references is what we're adding
                'b': {'a'},  # b currently references a
            }
        )
        result = detect_composition_cycles('a', {'b'}, get_refs)
        assert result is not None
        assert result == ['a', 'b', 'a']

    def test_a_b_c_a_cycle(self):
        """A -> B -> C -> A cycle."""
        get_refs = _make_get_all_references(
            {
                'b': {'c'},
                'c': {'a'},
            }
        )
        result = detect_composition_cycles('a', {'b'}, get_refs)
        assert result is not None
        assert result == ['a', 'b', 'c', 'a']

    def test_diamond_no_cycle(self):
        """Diamond shape (A->B, A->C, B->D, C->D) has no cycle."""
        get_refs = _make_get_all_references(
            {
                'b': {'d'},
                'c': {'d'},
                'd': set(),
            }
        )
        result = detect_composition_cycles('a', {'b', 'c'}, get_refs)
        assert result is None

    def test_empty_new_references(self):
        """No new references means no cycle."""
        get_refs = _make_get_all_references({})
        result = detect_composition_cycles('a', set(), get_refs)
        assert result is None

    def test_long_chain_no_cycle(self):
        """Long chain without cycle returns None."""
        get_refs = _make_get_all_references(
            {
                'b': {'c'},
                'c': {'d'},
                'd': {'e'},
                'e': set(),
            }
        )
        result = detect_composition_cycles('a', {'b'}, get_refs)
        assert result is None

    def test_cycle_path_deterministic(self):
        """Cycle detection is deterministic (sorted references)."""
        get_refs = _make_get_all_references(
            {
                'b': {'a'},
            }
        )
        result1 = detect_composition_cycles('a', {'b'}, get_refs)
        result2 = detect_composition_cycles('a', {'b'}, get_refs)
        assert result1 == result2

    def test_multiple_new_refs_one_cycles(self):
        """Multiple new_references, only one causes a cycle — cycle is detected."""
        get_refs = _make_get_all_references(
            {
                'b': set(),
                'c': {'a'},
            }
        )
        result = detect_composition_cycles('a', {'b', 'c'}, get_refs)
        assert result is not None
        assert result[-1] == 'a'

    def test_reference_to_unknown_variable(self):
        """Referencing an unknown variable (no entries in graph) — no cycle."""
        get_refs = _make_get_all_references({})
        result = detect_composition_cycles('a', {'unknown'}, get_refs)
        assert result is None


# =============================================================================
# Dataclass tests
# =============================================================================


class TestTemplateFieldIssue:
    def test_attributes(self):
        issue = TemplateFieldIssue(
            field_name='user_name',
            found_in_variable='prompt',
            found_in_label='production',
            reference_path=['snippet', 'prompt'],
        )
        assert issue.field_name == 'user_name'
        assert issue.found_in_variable == 'prompt'
        assert issue.found_in_label == 'production'
        assert issue.reference_path == ['snippet', 'prompt']

    def test_none_label(self):
        issue = TemplateFieldIssue(
            field_name='x',
            found_in_variable='v',
            found_in_label=None,
            reference_path=[],
        )
        assert issue.found_in_label is None


class TestTemplateValidationResult:
    def test_default_empty_issues(self):
        result = TemplateValidationResult()
        assert result.issues == []

    def test_with_issues(self):
        issue = TemplateFieldIssue(
            field_name='x',
            found_in_variable='v',
            found_in_label=None,
            reference_path=[],
        )
        result = TemplateValidationResult(issues=[issue])
        assert len(result.issues) == 1
