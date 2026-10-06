"""Tests for variable composition (@{variable_name}@ reference expansion)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import sys
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_handlebars import HandlebarsError

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.testing import TestExporter
from logfire.variables.composition import (
    VariableCompositionCycleError,
    VariableCompositionError,
    expand_references,
    find_references,
    find_references_and_errors,
)
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

# =============================================================================
# Tests for the pure composition functions (expand_references, find_references)
# =============================================================================


def _make_resolve_fn(
    variables: dict[str, str | None],
) -> Any:
    """Create a resolve_fn from a simple name->serialized_value dict."""

    def resolve_fn(ref_name: str) -> tuple[str | None, str | None, int | None, str]:
        if ref_name in variables:
            value = variables[ref_name]
            if value is None:
                return (None, None, None, 'unrecognized_variable')
            return (value, 'production', 1, 'resolved')
        return (None, None, None, 'unrecognized_variable')

    return resolve_fn


class TestExpandReferences:
    def test_invalid_serialized_value_is_returned_unchanged(self):
        """Non-JSON values cannot be composed and are returned as-is."""
        expanded, composed = expand_references('not json', 'my_var', _make_resolve_fn({}))

        assert expanded == 'not json'
        assert composed == []

    def test_no_references(self):
        """Values without @{}@ are returned unchanged."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"hello world"', 'my_var', resolve_fn)
        assert expanded == '"hello world"'
        assert composed == []

    def test_simple_string_reference(self):
        """Simple @{ref}@ expands to the referenced string value."""
        resolve_fn = _make_resolve_fn({'greeting': '"Hello"'})
        expanded, composed = expand_references('"@{greeting}@ World"', 'my_var', resolve_fn)
        assert expanded == '"Hello World"'
        assert len(composed) == 1
        assert composed[0].name == 'greeting'
        assert composed[0].value == 'Hello'
        assert composed[0].label == 'production'
        assert composed[0].version == 1
        assert composed[0].reason == 'resolved'
        assert composed[0].error is None

    def test_multiple_references(self):
        """Multiple @{refs}@ in one value are all expanded."""
        resolve_fn = _make_resolve_fn(
            {
                'greeting': '"Hello"',
                'name': '"World"',
            }
        )
        expanded, composed = expand_references('"@{greeting}@ @{name}@!"', 'my_var', resolve_fn)
        assert expanded == '"Hello World!"'
        assert {ref.name for ref in composed} == {'greeting', 'name'}

    def test_same_reference_multiple_times(self):
        """The same @{ref}@ used multiple times expands each occurrence."""
        resolve_fn = _make_resolve_fn({'word': '"echo"'})
        expanded, composed = expand_references('"@{word}@ @{word}@"', 'my_var', resolve_fn)
        assert expanded == '"echo echo"'
        # Handlebars resolves all occurrences in one pass, so only one ComposedReference
        assert len(composed) == 1
        assert composed[0].name == 'word'

    def test_nested_references(self):
        """References within referenced values are expanded recursively."""
        resolve_fn = _make_resolve_fn(
            {
                'a': '"Hello @{b}@"',
                'b': '"World"',
            }
        )
        expanded, composed = expand_references('"@{a}@!"', 'my_var', resolve_fn)
        assert expanded == '"Hello World!"'
        assert len(composed) == 1
        assert composed[0].name == 'a'
        assert composed[0].value == 'Hello World'
        assert len(composed[0].composed_from) == 1
        assert composed[0].composed_from[0].name == 'b'

    def test_nested_references_in_structured_value(self):
        """References within structured referenced values are expanded recursively."""
        resolve_fn = _make_resolve_fn(
            {
                'config': '{"prompt": "Hello @{name}@", "model": "gpt-4"}',
                'name': '"Alice"',
            }
        )
        expanded, composed = expand_references('"@{config.prompt}@ using @{config.model}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'Hello Alice using gpt-4'
        assert len(composed) == 1
        assert composed[0].name == 'config'
        assert composed[0].value == '{"prompt": "Hello Alice", "model": "gpt-4"}'
        assert len(composed[0].composed_from) == 1
        assert composed[0].composed_from[0].name == 'name'

    def test_cycle_detection(self):
        """Circular references are caught and the reference is left unexpanded."""
        resolve_fn = _make_resolve_fn(
            {
                'a': '"@{b}@"',
                'b': '"@{a}@"',
            }
        )
        # The cycle is caught inside expand_references; b tries to expand a
        # which is already in the visited set.
        _, composed = expand_references('"@{a}@"', 'my_var', resolve_fn)
        # a expands, but when b tries to expand @{a}@, it hits the cycle.
        # b is successfully resolved but its nested ref to a fails (cycle).
        assert len(composed) == 1
        assert composed[0].name == 'a'
        # b resolved but a inside b failed with cycle error
        assert len(composed[0].composed_from) == 1
        b_ref = composed[0].composed_from[0]
        assert b_ref.name == 'b'
        # b itself resolved, but its expansion of @{a}@ failed
        assert len(b_ref.composed_from) == 1
        assert b_ref.composed_from[0].name == 'a'
        assert b_ref.composed_from[0].error == 'Circular reference detected: my_var -> a -> b -> a'
        assert b_ref.composed_from[0].fatal is True  # cycles are fatal

    def test_self_reference_cycle(self):
        """A variable referencing itself is caught."""
        resolve_fn = _make_resolve_fn({'a': '"@{a}@"'})
        # my_var references a, a references itself
        _, composed = expand_references('"@{a}@"', 'my_var', resolve_fn)
        assert len(composed) == 1
        assert composed[0].name == 'a'
        # a resolved, but its self-reference @{a}@ failed with cycle
        assert len(composed[0].composed_from) == 1
        assert composed[0].composed_from[0].name == 'a'
        assert composed[0].composed_from[0].error == 'Circular reference detected: my_var -> a -> a'
        assert composed[0].composed_from[0].fatal is True  # cycles are fatal

    def test_depth_limit(self):
        """Chains exceeding MAX_COMPOSITION_DEPTH are caught."""
        # Build a chain: var_0 -> var_1 -> var_2 -> ... -> var_21
        variables: dict[str, str | None] = {}
        for i in range(22):
            if i < 21:
                variables[f'var_{i}'] = f'"@{{var_{i + 1}}}@"'
            else:
                variables[f'var_{i}'] = '"end"'
        resolve_fn = _make_resolve_fn(variables)
        _, composed = expand_references('"@{var_0}@"', 'my_var', resolve_fn)
        # Should have error about depth limit somewhere in the chain
        assert len(composed) == 1

        # Walk down the chain to find the depth error
        ref = composed[0]
        depth_error_found = False
        while ref.composed_from:
            if ref.error and 'Maximum composition depth' in ref.error:
                depth_error_found = True
                break
            ref = ref.composed_from[0]
        if not depth_error_found and ref.error:
            depth_error_found = 'Maximum composition depth' in ref.error
        assert depth_error_found, 'Expected depth limit error somewhere in the chain'

    def test_unresolvable_reference(self):
        """Under non-strict composition a missing reference renders as an empty string."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"Hello @{nonexistent}@"', 'my_var', resolve_fn)
        assert expanded == '"Hello "'
        assert len(composed) == 1
        assert composed[0].name == 'nonexistent'
        assert composed[0].value is None
        assert composed[0].reason == 'unrecognized_variable'
        assert composed[0].error is not None
        assert composed[0].fatal is False  # an unresolved reference is a soft (non-fatal) failure

    def test_unresolvable_reference_strict_raises(self):
        """Under strict composition a missing reference raises instead of rendering empty."""
        from pydantic_handlebars import HandlebarsError

        resolve_fn = _make_resolve_fn({})
        with pytest.raises(HandlebarsError):
            expand_references('"Hello @{nonexistent}@"', 'my_var', resolve_fn, strict=True)

    def test_unresolvable_dotted_reference(self):
        """A missing dotted reference also renders empty (non-strict)."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"Hello @{nonexistent.field}@"', 'my_var', resolve_fn)
        assert expanded == '"Hello "'
        assert len(composed) == 1
        assert composed[0].name == 'nonexistent'
        assert composed[0].value is None
        assert composed[0].reason == 'unrecognized_variable'

    def test_unresolvable_dotted_reference_alongside_resolved_ref(self):
        """A missing dotted ref renders empty without blocking other refs in the same value."""
        resolve_fn = _make_resolve_fn({'known': '"there"'})
        expanded, composed = expand_references('"Hi @{known}@ @{missing.field}@"', 'my_var', resolve_fn)
        assert expanded == '"Hi there "'
        assert {ref.name for ref in composed} == {'known', 'missing'}

    def test_unresolvable_simple_and_dotted_reference_same_base(self):
        """Simple and dotted unresolved refs for the same base both render empty (non-strict)."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"@{missing}@ @{missing.field}@"', 'my_var', resolve_fn)
        assert expanded == '" "'
        assert len(composed) == 1
        assert composed[0].name == 'missing'

    def test_resolved_dotted_ref_alongside_unresolved_simple_ref(self):
        """A dotted ref whose base resolves is rendered; a missing simple ref renders empty."""
        resolve_fn = _make_resolve_fn({'known': '{"field": "v"}'})
        expanded, composed = expand_references('"@{known.field}@ @{missing}@"', 'my_var', resolve_fn)
        assert expanded == '"v "'
        assert {ref.name for ref in composed} == {'known', 'missing'}

    def test_none_value_reference(self):
        """References to variables that don't resolve render empty (non-strict)."""
        resolve_fn = _make_resolve_fn({'missing': None})
        expanded, composed = expand_references('"Hello @{missing}@"', 'my_var', resolve_fn)
        assert expanded == '"Hello "'
        assert len(composed) == 1
        assert composed[0].value is None

    def test_non_string_reference(self):
        """Non-string variables (numbers) are rendered via Handlebars toString."""
        resolve_fn = _make_resolve_fn({'number': '42'})
        expanded, composed = expand_references('"Value: @{number}@"', 'my_var', resolve_fn)
        assert expanded == '"Value: 42"'
        assert len(composed) == 1
        assert composed[0].error is None

    def test_boolean_reference(self):
        """Boolean variables are rendered via Handlebars toString."""
        resolve_fn = _make_resolve_fn({'flag': 'true'})
        expanded, composed = expand_references('"Flag: @{flag}@"', 'my_var', resolve_fn)
        assert expanded == '"Flag: true"'
        assert len(composed) == 1
        assert composed[0].error is None

    def test_object_reference(self):
        """An object spliced whole into a string renders via pydantic-handlebars' `to_string`.

        That currently produces Python's `repr` of the decoded value (single quotes,
        `True`/`None`), NOT JSON and NOT JS's `[object Object]`. This is a known sharp edge
        — composing a whole object into a sentence is unusual (the common case is a dotted
        read like `@{obj.key}@`) — tracked upstream in pydantic-handlebars#14 for a possible
        `pydantic_core.to_json` switch. The assertion pins the actual behaviour so a future
        change is a conscious one.
        """
        resolve_fn = _make_resolve_fn({'obj': '{"key": "value"}'})
        expanded, composed = expand_references('"Data: @{obj}@"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == "Data: {'key': 'value'}"  # Python repr, not JSON
        assert len(composed) == 1
        assert composed[0].error is None

    def test_structured_type_with_references(self):
        """References inside JSON string values of structured types expand correctly."""
        resolve_fn = _make_resolve_fn({'safety': '"Be safe."'})
        serialized = json.dumps({'prompt': '@{safety}@ Always.', 'model': 'gpt-4'})
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        parsed = json.loads(expanded)
        assert parsed['prompt'] == 'Be safe. Always.'
        assert parsed['model'] == 'gpt-4'
        assert len(composed) == 1
        assert composed[0].name == 'safety'

    def test_list_with_references(self):
        """Composition walks lists and leaves non-string values unchanged."""
        resolve_fn = _make_resolve_fn({'greeting': '"Hello"', 'name': '"Alice"'})
        serialized = json.dumps(['@{greeting}@ @{name}@', 42, {'nested': '@{name}@'}])

        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)

        assert json.loads(expanded) == ['Hello Alice', 42, {'nested': 'Alice'}]
        assert {ref.name for ref in composed} == {'greeting', 'name'}

    def test_keyword_block_references_are_ignored(self):
        """Handlebars built-in names (`this`, helpers, `else`) aren't treated as variable references.

        `@{#if this}@yes@{/if}@` is a real Handlebars `if` block whose
        condition is the current context (`this`). It evaluates normally —
        with an empty context object (truthy in JS-style truthiness, which
        pydantic-handlebars follows) the body renders as `yes`. The
        important property under test is that no `composed` entries are
        produced — `this` and `if` are not resolved as variable lookups.
        This is surprising for Python users, so we may choose to revisit it,
        but for now `@{...}@` composition intentionally follows Handlebars
        truthiness rather than inventing Logfire-specific semantics.
        """
        expanded, composed = expand_references(json.dumps('@{#if this}@yes@{/if}@'), 'my_var', _make_resolve_fn({}))

        assert json.loads(expanded) == 'yes'
        assert composed == []

    def test_json_encoding_newlines(self):
        """Newlines in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'multi': '"Line1\\nLine2"'})
        expanded, _ = expand_references('"Before @{multi}@ After"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Before Line1\nLine2 After'

    def test_json_encoding_quotes(self):
        """Quotes in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'quoted': '"She said \\"hello\\""'})
        expanded, _ = expand_references('"@{quoted}@!"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'She said "hello"!'

    def test_json_encoding_unicode(self):
        """Unicode in referenced values works correctly."""
        resolve_fn = _make_resolve_fn({'emoji': json.dumps('Hello 🌍')})
        expanded, _ = expand_references('"@{emoji}@!"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Hello 🌍!'

    def test_json_encoding_backslashes(self):
        """Backslashes in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'path': json.dumps('C:\\Users\\test')})
        expanded, _ = expand_references('"Path: @{path}@"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Path: C:\\Users\\test'

    def test_escape_sequence(self):
        r"""Escaped \@{ is converted to literal @{.

        In serialized JSON, a literal backslash before @{ is encoded as \\@{.
        The regex lookbehind prevents matching, and post-processing converts \@{ to @{.
        """
        resolve_fn = _make_resolve_fn({'ref': '"expanded"'})
        # Build a JSON string that contains: not \@{ref}@ but @{ref}@
        # In JSON encoding, backslash must be \\, so the raw JSON is:
        # "not \\@{ref}@ but @{ref}@"
        raw_python_str = 'not \\@{ref}@ but @{ref}@'
        serialized = json.dumps(raw_python_str)
        # serialized is: "not \\@{ref}@ but @{ref}@"
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'not @{ref}@ but expanded'
        # Only the real ref (second one) is in composed
        assert len(composed) == 1
        assert composed[0].name == 'ref'

    def test_escape_only(self):
        r"""Only escaped references, no real references."""
        resolve_fn = _make_resolve_fn({})
        raw_python_str = 'literal \\@{tag}@'
        serialized = json.dumps(raw_python_str)
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'literal @{tag}@'
        assert composed == []

    def test_invalid_json_reference(self):
        """A reference to a value with invalid JSON renders empty (non-strict)."""
        resolve_fn = _make_resolve_fn({'bad': 'not json at all'})
        expanded, composed = expand_references('"@{bad}@"', 'my_var', resolve_fn)
        assert expanded == '""'
        assert len(composed) == 1
        assert composed[0].error is not None
        assert 'non-JSON' in composed[0].error


class TestFindReferences:
    def test_no_references(self):
        assert find_references('"hello world"') == []

    def test_single_reference(self):
        assert find_references('"@{greeting}@"') == ['greeting']

    def test_multiple_unique_references(self):
        # Sorted alphabetically — the parser doesn't surface source order, and
        # callers shouldn't depend on iteration-order-dependent behaviour.
        assert find_references('"@{c}@ @{a}@ @{b}@"') == ['a', 'b', 'c']

    def test_duplicate_references(self):
        """The same name appearing in multiple `@{ref}@` slots is deduplicated."""
        assert find_references('"@{b}@ @{a}@ @{b}@"') == ['a', 'b']

    def test_escaped_not_matched(self):
        assert find_references(r'"\\@{escaped}@"') == []

    def test_mixed_escaped_and_real(self):
        result = find_references(r'"\\@{escaped}@ @{real}@"')
        assert result == ['real']

    def test_in_structured_json(self):
        serialized = json.dumps({'prompt': '@{safety}@', 'other': '@{format}@'})
        assert find_references(serialized) == ['format', 'safety']

    def test_find_references_block_helpers(self):
        """find_references detects variable names from block helper syntax."""
        serialized = json.dumps('@{#if brand}@show@{else}@hide@{/if}@')
        result = find_references(serialized)
        assert 'brand' in result

    def test_find_references_block_and_simple(self):
        """find_references finds both simple and block-helper references."""
        serialized = json.dumps('@{greeting}@ @{#if flag}@yes@{/if}@')
        result = find_references(serialized)
        assert 'greeting' in result
        assert 'flag' in result

    def test_find_references_ignores_handlebars_keywords(self):
        serialized = json.dumps('@{this}@ @{#if this}@yes@{else}@no@{/if}@')
        assert find_references(serialized) == []

    def test_malformed_template_does_not_raise(self):
        """An unclosed block `@{#if x}@` contributes no refs instead of crashing find_references."""
        assert find_references(json.dumps('@{#if x}@')) == []

    def test_reserved_name_does_not_raise(self):
        """A reserved literal `@{true}@` (which the extractor asserts on) doesn't crash find_references."""
        assert find_references(json.dumps('@{true}@')) == []

    def test_find_references_and_errors_reports_malformed(self):
        """find_references_and_errors surfaces parse failures that find_references swallows."""
        refs, errors = find_references_and_errors(json.dumps('@{#if x}@'))
        assert refs == []
        assert len(errors) == 1
        assert 'could not be parsed' in errors[0]

    def test_find_references_and_errors_clean_value(self):
        """A well-formed value yields refs and no errors."""
        refs, errors = find_references_and_errors(json.dumps('@{a}@ @{b}@'))
        assert refs == ['a', 'b']
        assert errors == []

    def test_deeply_nested_value_does_not_recurse(self):
        """The decoded-value walk is iterative, so an arbitrarily deep structure doesn't RecursionError.

        This exercises the walk on the already-decoded value directly — the part this module is
        responsible for keeping total. We deliberately don't round-trip through ``json.dumps`` /
        ``json.loads`` here: json's own encode/decode is recursive with a much shallower limit (it
        overflows around depth ~1000 on CPython 3.10/3.11, where this test would otherwise fail in
        setup rather than in the code under test).
        """
        from logfire.variables.composition import _walk_references

        nested: Any = '@{x}@'
        for _ in range(5000):
            nested = [nested]
        refs, errors = _walk_references(nested)
        assert refs == {'x'}
        assert errors == []


def test_pydantic_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, 'pydantic', None)
    with pytest.raises(ImportError):
        logfire.var('foo', default='bar')


def test_pydantic_handlebars_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, 'pydantic_handlebars', None)
    with pytest.raises(ImportError):
        logfire.var('foo', default='bar')


# =============================================================================
# Tests for Handlebars-compatible @{}@ block helpers
# =============================================================================


class TestBlockHelpers:
    def test_block_if_true(self):
        """@{#if flag}@yes@{else}@no@{/if}@ with truthy flag."""
        resolve_fn = _make_resolve_fn({'flag': 'true'})
        expanded, composed = expand_references('"@{#if flag}@yes@{else}@no@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'yes'
        assert len(composed) == 1
        assert composed[0].name == 'flag'

    def test_block_if_false(self):
        """@{#if flag}@yes@{else}@no@{/if}@ with falsy flag."""
        resolve_fn = _make_resolve_fn({'flag': 'false'})
        expanded, composed = expand_references('"@{#if flag}@yes@{else}@no@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'no'
        assert len(composed) == 1
        assert composed[0].name == 'flag'

    def test_block_each(self):
        """@{#each items}@- @{this}@@{/each}@ iterates over a list."""
        resolve_fn = _make_resolve_fn({'items': '["a", "b", "c"]'})
        expanded, composed = expand_references('"@{#each items}@@{this}@ @{/each}@"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'a b c '
        assert len(composed) == 1
        assert composed[0].name == 'items'

    def test_block_unless(self):
        """@{#unless flag}@shown@{/unless}@ with falsy flag."""
        resolve_fn = _make_resolve_fn({'flag': 'false'})
        expanded, _ = expand_references('"@{#unless flag}@shown@{/unless}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'shown'

    def test_block_unless_truthy(self):
        """@{#unless flag}@shown@{/unless}@ with truthy flag shows nothing."""
        resolve_fn = _make_resolve_fn({'flag': 'true'})
        expanded, _ = expand_references('"@{#unless flag}@shown@{/unless}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == ''

    def test_block_with(self):
        """@{#with config}@@{name}@@{/with}@ accesses nested fields."""
        resolve_fn = _make_resolve_fn({'config': '{"name": "acme"}'})
        expanded, _ = expand_references('"@{#with config}@@{name}@@{/with}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'acme'

    def test_block_if_with_composition(self):
        """@{#if brand}@@{brand.tagline}@@{/if}@ — conditional with dotted access."""
        resolve_fn = _make_resolve_fn({'brand': '{"tagline": "Build faster"}'})
        expanded, _ = expand_references('"@{#if brand}@@{brand.tagline}@@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'Build faster'

    def test_block_if_missing_ref_is_falsy(self):
        """An unresolved `@{#if missing}@` is falsy (takes the else branch).

        Regression test: a missing reference used to be injected into the render
        context as the truthy literal string ``@{missing}@``, so `#if` wrongly
        took the *then* branch — leaking content guarded behind it. Missing refs
        are now left absent from the context, so they read as falsy like
        standard Handlebars.
        """
        resolve_fn = _make_resolve_fn({'flag': None})
        expanded, composed = expand_references('"@{#if flag}@SECRET@{else}@safe@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'safe'
        assert len(composed) == 1
        assert composed[0].name == 'flag'
        assert composed[0].fatal is False

    def test_block_if_missing_ref_no_else_renders_empty(self):
        """An unresolved `@{#if missing}@` with no else branch renders empty."""
        resolve_fn = _make_resolve_fn({'flag': None})
        expanded, _ = expand_references('"@{#if flag}@SECRET@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == ''

    def test_block_if_missing_dotted_ref_is_falsy(self):
        """An unresolved `@{#if missing.field}@` is falsy (takes the else branch)."""
        resolve_fn = _make_resolve_fn({'cfg': None})
        expanded, _ = expand_references('"@{#if cfg.enabled}@on@{else}@off@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'off'

    def test_block_unless_missing_ref_shows_body(self):
        """An unresolved `@{#unless missing}@` shows its body (missing is falsy)."""
        resolve_fn = _make_resolve_fn({'flag': None})
        expanded, _ = expand_references('"@{#unless flag}@shown@{/unless}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'shown'

    def test_block_each_missing_ref_is_empty(self):
        """An unresolved `@{#each missing}@` iterates zero times."""
        resolve_fn = _make_resolve_fn({'items': None})
        expanded, _ = expand_references('"@{#each items}@x@{/each}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == ''

    def test_missing_ref_interpolation_empty_alongside_falsy_block(self):
        """A missing ref renders empty when interpolated and is falsy in a control position (non-strict)."""
        resolve_fn = _make_resolve_fn({'name': None})
        expanded, composed = expand_references(
            '"Hi @{name}@! @{#if name}@VIP@{else}@guest@{/if}@ tail=@{name.title}@"', 'my_var', resolve_fn
        )
        assert json.loads(expanded) == 'Hi ! guest tail='
        assert len(composed) == 1
        assert composed[0].name == 'name'
        assert composed[0].fatal is False

    def test_reference_and_curly_placeholders_preserved(self):
        """@{greeting}@ expands, {{user.name}} is preserved for later rendering."""
        resolve_fn = _make_resolve_fn({'greeting': '"Hello"'})
        expanded, _ = expand_references('"@{greeting}@ {{user.name}}"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'Hello {{user.name}}'

    def test_escape_reference_syntax(self):
        r"""Escaped \@{ref}@ becomes literal @{ref}@ in output."""
        resolve_fn = _make_resolve_fn({'ref': '"expanded"'})
        raw_python_str = '\\@{ref}@'
        serialized = json.dumps(raw_python_str)
        expanded, _ = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == '@{ref}@'

    def test_escape_mixed(self):
        r"""Escaped \@{escaped}@ stays literal, real @{real}@ expands."""
        resolve_fn = _make_resolve_fn({'escaped': '"X"', 'real': '"expanded"'})
        raw_python_str = '\\@{escaped}@ @{real}@'
        serialized = json.dumps(raw_python_str)
        expanded, _ = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == '@{escaped}@ expanded'

    def test_referenced_html_entities_are_preserved(self):
        """Literal HTML entities in referenced values are not treated as internal escapes."""
        resolve_fn = _make_resolve_fn({'ref': json.dumps('literal &#123; and &#125;')})
        expanded, _ = expand_references('"@{ref}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'literal &#123; and &#125;'

    def test_referenced_escaped_reference_is_preserved(self):
        r"""Escaped reference syntax inside referenced values becomes the literal text post-render.

        Per `pydantic-handlebars >= 0.2.1` (and the Handlebars.js spec it
        matches), the escape `\@{...}@` consumes the backslash and emits
        the literal `@{...}@` in the output. The inner content is preserved
        — just unescaped of its backslash — so callers can author "this
        looks like a ref but render it literally" payloads.
        """
        resolve_fn = _make_resolve_fn({'ref': json.dumps(r'\@{not_a_ref}@')})
        expanded, _ = expand_references('"@{ref}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == '@{not_a_ref}@'


class TestExpandReferencesNativeHandlebarsSyntax:
    """Coverage for `@{}@` syntax that the previous regex-based renderer could not handle.

    These are now real Handlebars constructs against the configured
    `@{`/`}@` delimiter pair (see `pydantic_handlebars.HandlebarsEnvironment`),
    so the full set of helpers, dotted paths, and subexpressions works.
    """

    def test_dotted_path_in_block_helper_header(self):
        resolve_fn = _make_resolve_fn({'user': json.dumps({'active': True})})
        expanded, _ = expand_references('"@{#if user.active}@premium@{else}@free@{/if}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'premium'

    def test_each_iterates_top_level_list(self):
        resolve_fn = _make_resolve_fn({'tags': json.dumps(['a', 'b', 'c'])})
        expanded, _ = expand_references('"@{#each tags}@@{this}@;@{/each}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'a;b;c;'

    def test_each_with_parent_ref_reaches_top_context(self):
        resolve_fn = _make_resolve_fn(
            {
                'tags': json.dumps(['a', 'b']),
                'sep': json.dumps('-'),
            }
        )
        expanded, _ = expand_references('"@{#each tags}@@{this}@@{../sep}@@{/each}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'a-b-'

    def test_lookup_helper_with_two_args(self):
        resolve_fn = _make_resolve_fn(
            {
                'obj': json.dumps({'greeting': 'Hi'}),
                'key': json.dumps('greeting'),
            }
        )
        expanded, _ = expand_references('"@{lookup obj key}@"', 'my_var', resolve_fn)
        assert json.loads(expanded) == 'Hi'


class TestFindReferencesNativeHandlebarsSyntax:
    """`find_references` picks up the same set of refs the renderer would expand."""

    def test_dotted_path_in_block_helper_header_contributes_top_level(self):
        # `@{#if user.active}@` only references `user` at the top level.
        assert find_references('"@{#if user.active}@x@{/if}@"') == ['user']

    def test_each_block_helper_contributes_iterable_name(self):
        assert find_references('"@{#each tags}@@{this}@@{/each}@"') == ['tags']

    def test_lookup_helper_arguments_are_refs(self):
        assert find_references('"@{lookup obj key}@"') == ['key', 'obj']

    def test_known_helpers_are_not_treated_as_context_refs(self):
        # `if` / `each` / `lookup` are registered helpers; their names must
        # not appear in the dependency list. The `obj` / `key` arguments to
        # `lookup` here are scoped *inside* the `each items` block, so they
        # resolve against each iteration item rather than the top-level
        # context and are not top-level dependencies.
        refs = find_references('"@{#if cond}@@{#each items}@@{lookup obj key}@@{/each}@@{/if}@"')
        assert refs == ['cond', 'items']

    def test_lookup_args_at_top_level_are_refs(self):
        # When the helper call is at the top level (no enclosing context-
        # shifting block), its arguments are top-level deps.
        assert find_references('"@{lookup obj key}@"') == ['key', 'obj']


# =============================================================================
# Integration tests using LocalVariableProvider
# =============================================================================


def _make_variables_config(**variables: str | None) -> VariablesConfig:
    """Helper to create a VariablesConfig with simple string variables.

    Each kwarg is name=serialized_value (JSON string).
    """
    configs: dict[str, VariableConfig] = {}
    for name, value in variables.items():
        labels: dict[str, LabeledValue | LabelRef] = {}
        latest: LatestVersion | None = None
        if value is not None:
            labels['production'] = LabeledValue(version=1, serialized_value=value)
            latest = LatestVersion(version=1, serialized_value=value)
        configs[name] = VariableConfig(
            name=name,
            json_schema={'type': 'string'} if value is not None and value.startswith('"') else None,
            labels=labels,
            rollout=Rollout(labels={'production': 1.0}) if value is not None else Rollout(labels={}),
            overrides=[],
            latest_version=latest,
        )
    return VariablesConfig(variables=configs)


class TestCompositionIntegration:
    def test_simple_reference(self, config_kwargs: dict[str, Any]):
        """End-to-end: variable with @{ref}@ is resolved with composition."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"@{greeting}@ World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Hello World'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].value == 'Hello'

    def test_code_default_reference_across_with_settings_siblings(self, config_kwargs: dict[str, Any]):
        """Code-default composition sees variables registered on with_settings() siblings."""
        lf = logfire.configure(**config_kwargs)
        lf2 = lf.with_settings(tags=['other'])

        lf.var(name='greeting', default='Hello', type=str)
        main = lf2.var(name='main', default='@{greeting}@ World', type=str)

        result = main.get()

        assert result.value == 'Hello World'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].value == 'Hello'

    def test_override_participates_in_composition(self, config_kwargs: dict[str, Any]):
        """An override value containing @{ref}@ is expanded against the live config.

        Overrides run through the same compose → render → deserialize pipeline as a stored
        value, so an override can stand in for a candidate stored value (e.g. during iterative
        optimization) and resolve identically to how it would once pushed.
        """
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"@{greeting}@ World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        with var.override('Hi @{greeting}@!'):
            result = var.get()

        assert result.value == 'Hi Hello!'  # @{greeting}@ expanded in the override
        assert result.reason == 'context_override'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].value == 'Hello'

    def test_escape_only_value_is_unescaped_consistently(self, config_kwargs: dict[str, Any]):
        r"""Escape behaviour matches whether or not another real `@{ref}@` is present.

        Regression for #1951 r3288986490 — a value containing only an escaped
        `\@{baz}@` used to keep its backslash, while the same escape combined
        with a real reference produced literal `@{baz}@`. After dropping the
        `has_references` short-circuit both go through the unescape path.
        """
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        # No real refs — must still unescape.
        bar2 = lf.var(name='bar2', default=r'\@{baz}@', type=str)
        assert bar2.get().value == '@{baz}@'

        # Escape + real ref — both unescape (existing behaviour, asserted as a
        # consistency anchor with the previous case).
        baz = lf.var(name='baz', default='BAZ', type=str)
        bar3 = lf.var(name='bar3', default=r'@{baz}@ and \@{baz}@', type=str)
        assert bar3.get().value == 'BAZ and @{baz}@'

        # Used in the test_simple_reference style: silence unused-var warning
        # by referencing `baz` once.
        assert baz.get().value == 'BAZ'

    def test_backslash_run_parity_under_composition(self, config_kwargs: dict[str, Any]):
        r"""Even-length backslash runs render the mustache; odd-length escape it.

        Regression for the bug exposed by pydantic-handlebars 0.2.1 — the
        previous logfire-side `has_references` regex treated *any* preceding
        backslash as the escape marker, so `\\@{x}@` (two backslashes) was
        seen as "no refs" and rendered as-is. With 0.2.1's spec-compliant
        renderer plus the simplified `'@{' in v` gate, both odd and even
        runs route through the renderer and resolve per Handlebars.js rules:

          N backslashes contributes N // 2 literal `\` characters; parity
          decides whether the mustache renders (even) or stays literal (odd).
        """
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        lf.var(name='x', default='X', type=str)

        # 1 backslash → escape mustache, no literal backslash in output.
        one = lf.var(name='one', default=r'\@{x}@', type=str)
        assert one.get().value == '@{x}@'

        # 2 backslashes → one literal backslash, then mustache renders.
        two = lf.var(name='two', default=r'\\@{x}@', type=str)
        assert two.get().value == r'\X'

        # 3 backslashes → one literal backslash, then escape mustache.
        three = lf.var(name='three', default=r'\\\@{x}@', type=str)
        assert three.get().value == r'\@{x}@'

        # 4 backslashes → two literal backslashes, then mustache renders.
        four = lf.var(name='four', default=r'\\\\@{x}@', type=str)
        assert four.get().value == r'\\X'

    def test_composition_exception_falls_back(self, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
        """Composition engine failures fall back to the code default."""
        variables_config = _make_variables_config(
            main='"@{greeting}@ World"',
            greeting='"Hello"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        def raise_composition_error(*args: Any, **kwargs: Any) -> Any:
            raise VariableCompositionError('forced composition failure')

        monkeypatch.setattr('logfire.variables.variable.expand_references', raise_composition_error)

        var = lf.var(name='main', default='fallback', type=str)
        with pytest.warns(RuntimeWarning, match='composition failed'):
            result = var.get()

        assert result.value == 'fallback'
        assert result.exception is not None
        assert result.reason == 'other_error'

    def test_validation_failure_reason_is_filter_independent(self, config_kwargs: dict[str, Any]):
        """Under `filterwarnings=error`, a validation failure still reports reason='validation_error'.

        Regression for the warning/`except` coupling (B1): a soft `RuntimeWarning` escalated to an
        error by `-W error` used to be caught by the broad fallback `except` in `_resolve`,
        replacing the computed result with `reason='other_error'` and the `RuntimeWarning` as its
        exception. `_emit_resolution_warning` now suppresses that escalation so resolution is
        filter-independent.
        """
        import warnings as _warnings

        from pydantic import ValidationError

        variables_config = _make_variables_config(main='"not an int"')
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='main', default=0, type=int)
        with _warnings.catch_warnings():
            _warnings.simplefilter('error')
            result = var.get()
        assert result.reason == 'validation_error'
        assert result.value == 0
        assert isinstance(result.exception, ValidationError)

    def test_malformed_composition_value_falls_back(self, config_kwargs: dict[str, Any]):
        """A malformed `@{...}@` stored value falls back to the code default instead of crashing (A3).

        `@{#if x}@` (unclosed) makes pydantic-handlebars raise while rendering during resolution;
        `_try_resolve` catches it and routes to the code-default fallback with a warning,
        carrying the real parse error on `.exception` rather than letting it escape uncaught.
        """
        variables_config = _make_variables_config(main='"@{#if x}@ oops"')
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='main', default='fallback', type=str)
        with pytest.warns(RuntimeWarning, match='composition failed'):
            result = var.get()
        assert result.value == 'fallback'
        assert result.reason == 'other_error'
        assert isinstance(result.exception, HandlebarsError)

    def test_callable_default_invoked_once_on_composition_failure(
        self, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ):
        """A callable default must not be re-invoked on the composition-failure fallback path.

        Regression for #1954 r3287513610 — when the code-default tier
        supplies the value AND composition then fails, both the
        serialize step (in `_lookup_serialized` → `_get_serialized_default`)
        and the fallback step (in `_resolve_code_default_value`) previously
        invoked the callable, doubling side effects. With `_DEFAULT_CACHE`
        in place the callable is invoked once per `get()`.
        """
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        call_count = 0

        def make_default(targeting_key: str | None, attributes: Any) -> str:
            nonlocal call_count
            call_count += 1
            # Returns a value that contains a reference, so composition
            # runs against it; we force composition to fail below so the
            # fallback path also needs the default.
            return '@{missing_for_test}@'

        # Provider has nothing; code default (the callable above) supplies
        # the serialized value. Then we force composition to fail.
        def raise_composition_error(*args: Any, **kwargs: Any) -> Any:
            raise VariableCompositionError('forced composition failure')

        monkeypatch.setattr('logfire.variables.variable.expand_references', raise_composition_error)

        var = lf.var(name='callable_default', default=make_default, type=str)
        with pytest.warns(RuntimeWarning, match='composition failed'):
            result = var.get()

        assert result.reason == 'other_error'
        assert call_count == 1, f'callable default invoked {call_count} times, expected 1'

    def test_failing_callable_default_invoked_once_per_get(self, config_kwargs: dict[str, Any]):
        """A callable default that *raises* is invoked only once per `get()`.

        Regression for #1954 r3296066209 — `_get_default_cached` originally
        cached only successful values, so a raising callable escaped the
        cache and could be re-invoked up to three times in one `get()`
        (once each in `_get_serialized_default`, `_resolve_code_default`,
        and the outer-`except` fallback). The cache now records the
        exception too and re-raises it on subsequent lookups.
        """
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        call_count = 0

        def always_raises(targeting_key: str | None, attributes: Any) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError('default unavailable')

        var = lf.var(name='failing_default', default=always_raises, type=str)
        # The code default itself raised, so there's nothing to fall back to: `get()`
        # returns `None` but warns loudly rather than swallowing the error silently.
        with pytest.warns(RuntimeWarning, match='could not be resolved and its code default raised'):
            result = var.get()

        assert result.value is None
        assert result.reason == 'other_error'
        assert isinstance(result.exception, RuntimeError)
        assert call_count == 1, f'failing callable invoked {call_count} times, expected 1'

    def test_nested_reference(self, config_kwargs: dict[str, Any]):
        """A→B→C chain resolves fully."""
        variables_config = _make_variables_config(
            c='"end"',
            b='"@{c}@_b"',
            a='"@{b}@_a"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='a', default='fallback', type=str)
        result = var.get()
        assert result.value == 'end_b_a'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'b'
        assert result.composed_from[0].composed_from[0].name == 'c'

    def test_cycle_falls_back_gracefully(self, config_kwargs: dict[str, Any]):
        """Cycles in references are surfaced on the top-level result and a warning is emitted."""
        variables_config = _make_variables_config(
            a='"@{b}@"',
            b='"@{a}@"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='a', default='fallback', type=str)
        with pytest.warns(RuntimeWarning, match='composition failed'):
            result = var.get()
        assert result.value == 'fallback'
        assert isinstance(result.exception, VariableCompositionError)
        assert result.reason == 'other_error'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].composed_from[0].error == 'Circular reference detected: a -> b -> a'

    def test_nonexistent_reference_in_provider_value_falls_back_to_code_default(self, config_kwargs: dict[str, Any]):
        """A missing `@{ref}@` in a provider value falls back to the code default.

        Provider/stored values are composed in strict mode, so an unresolvable reference is
        treated like any other composition failure: the value is discarded and resolution
        falls back to the variable's code default, with a RuntimeWarning naming the reference.
        (Contrast `test_code_default_with_unresolved_reference_renders_empty`, where the
        *code default* is the lenient last resort and a missing reference renders empty.)
        """
        variables_config = _make_variables_config(
            main='"Hello @{nonexistent}@"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        with pytest.warns(RuntimeWarning, match='composition failed; falling back to code default'):
            result = var.get()
        assert result.value == 'fallback'  # discarded the broken provider value for the code default
        assert result.reason == 'other_error'
        assert result.exception is not None
        assert 'nonexistent' in str(result.exception)

    def test_non_string_reference_expanded(self, config_kwargs: dict[str, Any]):
        """Non-string variables are now expanded via Handlebars."""
        # Create a variable config with a non-string variable
        configs: dict[str, VariableConfig] = {
            'number': VariableConfig(
                name='number',
                json_schema={'type': 'integer'},
                labels={'production': LabeledValue(version=1, serialized_value='42')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='42'),
            ),
            'main': VariableConfig(
                name='main',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"Value: @{number}@"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='"Value: @{number}@"'),
            ),
        }
        variables_config = VariablesConfig(variables=configs)
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Value: 42'

    def test_structured_type_composition(self, config_kwargs: dict[str, Any]):
        """Composition works in string fields of Pydantic models."""

        class AgentConfig(BaseModel):
            prompt: str
            model: str

        safety_value = json.dumps('Be safe.')
        agent_value = json.dumps({'prompt': '@{safety}@ Always.', 'model': 'gpt-4'})

        configs: dict[str, VariableConfig] = {
            'safety': VariableConfig(
                name='safety',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value=safety_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value=safety_value),
            ),
            'agent_config': VariableConfig(
                name='agent_config',
                json_schema=None,
                labels={'production': LabeledValue(version=1, serialized_value=agent_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value=agent_value),
            ),
        }
        variables_config = VariablesConfig(variables=configs)
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='agent_config', default=AgentConfig(prompt='default', model='default'), type=AgentConfig)
        result = var.get()
        assert result.value.prompt == 'Be safe. Always.'
        assert result.value.model == 'gpt-4'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'safety'

    def test_no_composition_for_context_override(self, config_kwargs: dict[str, Any]):
        """Context overrides return typed values directly, no composition."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"@{greeting}@ World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        with var.override('override_value'):
            result = var.get()
            assert result.value == 'override_value'
            assert result.composed_from == []
            assert result.reason == 'context_override'

    def test_composition_with_explicit_label(self, config_kwargs: dict[str, Any]):
        """Composition works when using explicit label parameter."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"@{greeting}@ World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get(label='production')
        assert result.value == 'Hello World'
        assert len(result.composed_from) == 1

    def test_span_attributes_with_composition(self, config_kwargs: dict[str, Any], exporter: TestExporter):
        """Span attributes include composed_from when composition occurs."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"@{greeting}@ World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        exporter.clear()

        result = var.get()
        assert result.value == 'Hello World'

        # Find the completed span for 'main' variable resolution (last one with this name)
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable main']
        main_span = resolve_spans[-1]  # last = completed span
        attrs = dict(main_span.attributes or {})

        # Check composed_from attribute
        composed_from_json = attrs.get('composed_from')
        assert isinstance(composed_from_json, str)
        composed_data = json.loads(composed_from_json)
        assert len(composed_data) == 1
        assert composed_data[0]['name'] == 'greeting'
        assert composed_data[0]['version'] == 1
        assert composed_data[0]['label'] == 'production'

    def test_span_attributes_include_nested_composition_chain(
        self, config_kwargs: dict[str, Any], exporter: TestExporter
    ):
        """Span attributes include nested composed_from entries, matching the resolution result."""
        variables_config = _make_variables_config(
            leaf='"LEAF"',
            middle='"middle wraps @{leaf}@"',
            main='"top: @{middle}@"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        exporter.clear()

        result = var.get()
        assert result.value == 'top: middle wraps LEAF'
        assert result.composed_from[0].composed_from[0].name == 'leaf'

        resolve_spans = [s for s in exporter.exported_spans if s.name == 'Resolve variable main']
        attrs = dict(resolve_spans[-1].attributes or {})
        composed_from_json = attrs.get('composed_from')
        assert isinstance(composed_from_json, str)
        composed_data = json.loads(composed_from_json)

        assert composed_data[0]['name'] == 'middle'
        assert composed_data[0]['composed_from'][0]['name'] == 'leaf'
        assert composed_data[0]['composed_from'][0]['version'] == 1

    def test_span_attributes_without_composition(self, config_kwargs: dict[str, Any], exporter: TestExporter):
        """Span attributes do NOT include composed_from when no composition occurs."""
        variables_config = _make_variables_config(
            main='"no refs here"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        exporter.clear()

        var.get()

        # Find the completed span for 'main' variable resolution (last one with this name)
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable main']
        main_span = resolve_spans[-1]  # last = completed span
        attrs = dict(main_span.attributes or {})
        assert 'composed_from' not in attrs

    @pytest.mark.parametrize('register_main', [False, True], ids=['unregistered', 'registered_no_selected_value'])
    def test_code_default_composition_when_provider_has_no_value(
        self, config_kwargs: dict[str, Any], register_main: bool
    ):
        """References in code defaults are expanded when a provider has no selected value."""
        variables_config = _make_variables_config(main=None) if register_main else VariablesConfig(variables={})
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        lf.var(name='greeting', default='Hello', type=str)
        var = lf.var(name='main', default='@{greeting}@ fallback', type=str)
        result = var.get()
        assert result.value == 'Hello fallback'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].reason == 'code_default'

    def test_top_level_reason_is_code_default_when_provider_has_no_value(self, config_kwargs: dict[str, Any]):
        """When the provider has no value for the parent, the resolution reason is 'code_default'."""
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='parent', default='hello', type=str)
        result = var.get()
        assert result.value == 'hello'
        assert result.reason == 'code_default'

    def test_reference_falls_back_to_registered_code_default(self, config_kwargs: dict[str, Any]):
        """A composed reference uses a registered variable's default when the provider has no selected value."""
        variables_config = VariablesConfig(
            variables={
                'main': VariableConfig(
                    name='main',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"@{greeting}@ from provider"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
                'greeting': VariableConfig(
                    name='greeting',
                    json_schema={'type': 'string'},
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        lf.var(name='greeting', default='Hello', type=str)
        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Hello from provider'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].reason == 'code_default'

    def test_override_propagates_through_composition(self, config_kwargs: dict[str, Any]):
        """`var.override(...)` is honoured for `@{var}@` substitutions in a parent variable."""
        variables_config = VariablesConfig(
            variables={
                'greeting': VariableConfig(
                    name='greeting',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"PROVIDER_GREETING"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
                'parent': VariableConfig(
                    name='parent',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"hello @{greeting}@"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        greeting = lf.var(name='greeting', default='code_default_greeting', type=str)
        parent = lf.var(name='parent', default='fallback', type=str)

        # Without override: provider value used.
        assert parent.get().value == 'hello PROVIDER_GREETING'

        # With override on the referenced variable, composition sees the overridden value.
        with greeting.override('OVERRIDDEN_GREETING'):
            assert greeting.get().value == 'OVERRIDDEN_GREETING'
            result = parent.get()
            assert result.value == 'hello OVERRIDDEN_GREETING'
            assert len(result.composed_from) == 1
            assert result.composed_from[0].name == 'greeting'
            assert result.composed_from[0].reason == 'context_override'

    def test_resolve_function_override_propagates_through_composition(self, config_kwargs: dict[str, Any]):
        """A ResolveFunction passed to `override(...)` is called when used via composition."""
        variables_config = VariablesConfig(
            variables={
                'parent': VariableConfig(
                    name='parent',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"hello @{greeting}@"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        greeting = lf.var(name='greeting', default='code_default_greeting', type=str)
        parent = lf.var(name='parent', default='fallback', type=str)

        def compute_greeting(targeting_key: Any, attributes: Any) -> str:
            return 'DYNAMIC_GREETING'

        with greeting.override(compute_greeting):
            result = parent.get()
            assert result.value == 'hello DYNAMIC_GREETING'
            assert result.composed_from[0].reason == 'context_override'

    def test_unserializable_override_falls_through_to_provider(self, config_kwargs: dict[str, Any]):
        """An override that fails to serialize via the child's type adapter falls through."""
        variables_config = VariablesConfig(
            variables={
                'parent': VariableConfig(
                    name='parent',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"hello @{opaque}@"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        # `object` types can't be JSON-serialized via pydantic, so the override fails
        # to serialize and the lookup falls through to the registered code default.
        opaque = lf.var(name='opaque', default='code_default_opaque', type=object)
        parent = lf.var(name='parent', default='fallback', type=str)

        with opaque.override(object()):
            with pytest.warns(RuntimeWarning, match='could not be serialized'):
                result = parent.get()
            # Override failed to serialize; falls through to provider (which has nothing)
            # then to opaque's registered code default.
            assert result.value == 'hello code_default_opaque'
            assert result.composed_from[0].reason == 'code_default'

    def test_provider_value_falls_back_when_referenced_default_unserializable(self, config_kwargs: dict[str, Any]):
        """If a `@{ref}@` resolves to nothing (its code default can't serialize), fall back."""
        variables_config = VariablesConfig(
            variables={
                'parent': VariableConfig(
                    name='parent',
                    json_schema={'type': 'string'},
                    labels={'production': LabeledValue(version=1, serialized_value='"hello @{opaque}@"')},
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        # A registered variable whose code default can't be JSON-serialized.
        lf.var(name='opaque', default=object(), type=object)
        parent = lf.var(name='parent', default='fallback', type=str)

        with pytest.warns(RuntimeWarning, match='composition failed; falling back to code default'):
            result = parent.get()
        # `@{opaque}@` produced no JSON value from any tier, so the strict provider value
        # fails composition and resolution falls back to parent's own code default.
        assert result.value == 'fallback'
        assert result.reason == 'other_error'
        assert result.exception is not None
        assert 'opaque' in str(result.exception)


class TestCodeDefaultSerializationFailures:
    """Cover paths where a variable's own code default can't be serialized."""

    def test_unserializable_default_skips_default_composition(self, config_kwargs: dict[str, Any]):
        """A non-serializable code default falls through to the plain `_get_default` value."""
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        sentinel = object()
        var = lf.var(name='opaque', default=sentinel, type=object)
        result = var.get()
        # `_get_serialized_default` returned None, so composition is skipped and the plain
        # Python default flows through.
        assert result.value is sentinel
        assert result.reason == 'code_default'

    def test_code_default_with_unresolved_reference_renders_empty(self, config_kwargs: dict[str, Any]):
        """A code default that references a missing variable renders the reference as empty.

        The code default is the lenient last resort: when its strict composition fails, it is
        re-composed non-strict so the unresolvable `@{nonexistent}@` becomes an empty string
        (there is nothing further to fall back to). The value still comes from the code-default
        tier, so the reason stays 'code_default'.
        """
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='hello @{nonexistent}@', type=str)
        with pytest.warns(RuntimeWarning, match='code default has unresolved composition reference'):
            result = var.get()
        assert result.value == 'hello '
        assert result.reason == 'code_default'


class TestCompositionExceptions:
    """Test the exception hierarchy."""

    def test_composition_error_is_exception(self):
        assert issubclass(VariableCompositionError, Exception)

    def test_cycle_error_is_composition_error(self):
        assert issubclass(VariableCompositionCycleError, VariableCompositionError)

    def test_direct_cycle_error(self):
        with pytest.raises(VariableCompositionCycleError, match='Circular reference'):
            expand_references(
                '"test"',
                'a',
                _make_resolve_fn({}),
                _visited=('a',),
            )

    def test_direct_depth_error(self):
        with pytest.raises(VariableCompositionError, match='Maximum composition depth'):
            expand_references(
                '"test"',
                'a',
                _make_resolve_fn({}),
                _depth=21,
            )


class _Inputs(BaseModel):
    name: str


class TestTemplateIntoPlainCompositionWarning:
    """A variable without inputs_type that composes a template variable warns at declaration time."""

    def test_plain_var_composing_template_var_warns(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        lf.template_var(name='bar', default='Hi {{name}}', type=str, inputs_type=_Inputs)
        with pytest.warns(RuntimeWarning, match="'foo' composes template variable 'bar'"):
            lf.var(name='foo', default='Greeting: @{bar}@', type=str)

    def test_warns_regardless_of_declaration_order(self, config_kwargs: dict[str, Any]):
        # The plain variable is declared *first*, before the template variable exists; the warning
        # still fires when the template variable is later declared (the check runs in both directions).
        lf = logfire.configure(**config_kwargs)
        # An unrelated plain var that does NOT compose the template var — the reverse-direction scan
        # must skip it without warning.
        lf.var(name='unrelated', default='nothing to see here', type=str)
        lf.var(name='foo', default='Greeting: @{bar}@', type=str)
        with pytest.warns(RuntimeWarning, match="'foo' composes template variable 'bar'"):
            lf.template_var(name='bar', default='Hi {{name}}', type=str, inputs_type=_Inputs)

    def test_template_var_composing_template_var_does_not_warn(self, config_kwargs: dict[str, Any]):
        import warnings as _warnings

        lf = logfire.configure(**config_kwargs)
        lf.template_var(name='bar', default='Hi {{name}}', type=str, inputs_type=_Inputs)
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter('always')
            lf.template_var(name='foo', default='Greeting: @{bar}@', type=str, inputs_type=_Inputs)
        assert not [w for w in caught if 'composes template variable' in str(w.message)]

    def test_plain_var_composing_plain_var_does_not_warn(self, config_kwargs: dict[str, Any]):
        import warnings as _warnings

        lf = logfire.configure(**config_kwargs)
        lf.var(name='bar', default='there', type=str)
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter('always')
            lf.var(name='foo', default='Hi @{bar}@', type=str)
        assert not [w for w in caught if 'composes template variable' in str(w.message)]
