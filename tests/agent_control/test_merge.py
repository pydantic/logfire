"""Code < published < the values a run passed explicitly, and a record of which layer won."""

from __future__ import annotations

from logfire.agent_control import merge_settings


def test_published_beats_code_and_leaves_untouched_keys_alone() -> None:
    merged = merge_settings({'temperature': 0.2, 'max_tokens': 1024}, {'temperature': 0.8})
    assert merged.settings == {'temperature': 0.8, 'max_tokens': 1024}
    assert merged.sources == {'temperature': 'published', 'max_tokens': 'code'}


def test_a_run_that_passes_the_code_value_explicitly_still_beats_the_published_one() -> None:
    # The case diffing cannot express, and the reason this function takes the explicit keys instead
    # of recovering them: `0.2` from the run is indistinguishable from `0.2` inherited from the code.
    merged = merge_settings({'temperature': 0.2}, {'temperature': 0.8}, {'temperature': 0.2})
    assert merged.settings == {'temperature': 0.2}
    assert merged.source('temperature') == 'run'


def test_a_run_can_explicitly_clear_a_key_the_layers_under_it_set() -> None:
    merged = merge_settings({'timeout': 30}, {'timeout': 60}, {'timeout': None})
    assert merged.settings == {}
    # Named in `sources` and absent from `settings`: "send no value for this" is not the same thing
    # as "nobody ever set this", and an adapter has to be able to tell them apart.
    assert merged.sources == {'timeout': 'run'}


def test_an_unset_key_in_code_or_published_is_absent_rather_than_a_deliberate_clearing() -> None:
    # A framework that spells its unset settings out as `None` must not erase the layer under it.
    merged = merge_settings({'temperature': None, 'max_tokens': 1024}, {'temperature': 0.8, 'max_tokens': None})
    assert merged.settings == {'temperature': 0.8, 'max_tokens': 1024}
    assert merged.sources == {'temperature': 'published', 'max_tokens': 'code'}


def test_keys_outside_the_contract_survive_with_their_provenance() -> None:
    # An adapter merges its framework's whole settings object rather than splitting first.
    merged = merge_settings({'extra_headers': {'x': '1'}}, {'temperature': 0.8})
    assert merged.settings == {'extra_headers': {'x': '1'}, 'temperature': 0.8}
    assert merged.source('extra_headers') == 'code'


def test_merging_nothing_is_an_empty_patch_with_nothing_to_say() -> None:
    merged = merge_settings()
    assert (merged.settings, merged.sources) == ({}, {})
    assert merged.source('temperature') is None
