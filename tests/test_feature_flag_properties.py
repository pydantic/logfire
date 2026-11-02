"""Property checks for rule selection, weighted assignment, and reference traversal."""

# pyright: reportPrivateUsage=false
from itertools import accumulate, product
from random import Random
from unittest.mock import patch

from hypothesis import example, given, settings, strategies as st

from logfire.variables.config import LabeledValue, LabelRef, Rollout, RolloutOverride, ValueEquals, VariableConfig


@settings(max_examples=500, deadline=None)
@given(st.lists(st.lists(st.booleans(), max_size=8), max_size=30))
@example([])
@example([[], [True]])
@example([[False], [True], [True]])
def test_first_matching_rollout(conditions: list[list[bool]]) -> None:
    config = VariableConfig(
        name='flag',
        rollout=Rollout(),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='enabled', value=value) for value in values],
                rollout=Rollout(),
            )
            for values in conditions
        ],
    )
    # Empty conjunctions match, and the earliest matching rule owns the result.
    index = next((i for i, values in enumerate(conditions) if all(values)), None)
    expected = config.rollout if index is None else config.overrides[index].rollout
    actual, matched = config._select_rollout_with_match({'enabled': True})
    assert actual is expected
    assert matched is (index is not None)


@settings(max_examples=500, deadline=None)
@given(st.lists(st.integers(0, 16), max_size=16).filter(lambda weights: sum(weights) <= 16))
@example([])
@example([0, 16, 0])
@example([8, 0, 8])
@example([15])
def test_weighted_assignment_matches_integer_intervals(weights: list[int]) -> None:
    labels = [f'label_{i}' for i in range(len(weights))]
    # Fill the unassigned portion with the code default. Integer intervals are
    # independent of random.choices and exactly representable as binary floats.
    mass = [*weights, 16 - sum(weights)]
    population = [*labels, None]
    boundaries = list(accumulate(mass))
    rollout = Rollout(labels=dict(zip(labels, (weight / 16 for weight in weights))))
    with patch.object(Random, 'random') as draw:
        for ticket in range(16):
            expected = next(population[i] for i, end in enumerate(boundaries) if ticket < end)
            draw.return_value = ticket / 16
            assert rollout.select_label('scripted_draw') == expected


@st.composite
def reference_graphs(draw: st.DrawFn) -> list[int]:
    size = draw(st.integers(1, 40))
    return draw(st.lists(st.integers(-2, size - 1), min_size=size, max_size=size))


def check_reference_graph(edges: list[int], start: int) -> None:
    config = VariableConfig(
        name='flag',
        labels={
            f'label_{i}': (
                LabeledValue(version=1, serialized_value=str(i))
                if edge == -1
                else LabelRef(ref='code_default' if edge == -2 else f'label_{edge}')
            )
            for i, edge in enumerate(edges)
        },
        rollout=Rollout(),
        overrides=[],
    )
    # A walk longer than the number of labels must repeat a node. This oracle
    # uses a fixed bound, not the implementation's visited-set cycle detection.
    current = start
    expected = None
    for _ in range(len(edges) + 1):
        edge = edges[current]
        if edge < 0:
            expected = str(current) if edge == -1 else None
            break
        current = edge
    assert config.follow_ref(config.labels[f'label_{start}']) == (
        expected,
        1 if expected is not None else None,
    )


@settings(max_examples=500, deadline=None)
@given(reference_graphs())
@example([0])
@example([1, 0])
@example([1, 2, -1])
@example([1, 2, -2])
def test_reference_resolution_matches_bounded_walk(edges: list[int]) -> None:
    check_reference_graph(edges, 0)


def test_reference_resolution_for_all_small_graphs() -> None:
    for size in range(1, 5):
        for edges in product(range(-2, size), repeat=size):
            for start in range(size):
                check_reference_graph(list(edges), start)
