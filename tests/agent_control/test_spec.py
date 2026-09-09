"""The cross-language vectors, run against this core.

Three things have to give the same answer in Python and TypeScript, because a Logfire project is
shared and the SDKs are not: which variable an agent's config lives in, what a code baseline says,
and what a published value parses to. `spec/` is where those answers live, and this is the half of
the agreement this package keeps. A change to a rule changes the file first, and both cores after.

The agent-name vectors are exercised in `test_control.py`, where the naming is public API.
"""

from __future__ import annotations

import hashlib
import warnings
from typing import Any

import pytest

from logfire.agent_control import AgentConfig, Block, ToolDef, build_baseline
from logfire.agent_control._reporting import reset_warned_messages

from .conftest import SPEC, expand_repeats

# A distinctive fragment of each warning, mapped to the code the vectors name it by. Both cores word
# their warnings for their own users; what has to match is which decision was taken.
CODES: list[tuple[str, str]] = [
    ('selects invalid model', 'invalid-model'),
    ('Managed instructions section contains', 'instructions-section-too-long'),
    ("instructions section is invalid -- instructions=''", 'instructions-section-empty'),
    ('instructions section has invalid container', 'instructions-invalid-container'),
    ('Managed instruction entry contains', 'instruction-entry-too-long'),
    ('has neither an `id` to address nor text to add', 'instruction-entry-empty'),
    ('Managed instruction entry', 'instruction-entry-invalid'),
    ('settings section has invalid container', 'settings-invalid-container'),
    ('which this version of the SDK does not recognize', 'setting-value-not-recognized'),
    ('has invalid value', 'setting-value-invalid'),
    ('tool definitions section has invalid container', 'tool-definitions-invalid-container'),
    ('tool definition override', 'tool-definition-invalid'),
    ('The agent runs with a request timeout', 'baseline-timeout-not-representable'),
    ('The agent runs with', 'baseline-value-not-describable'),
]


def code_of(message: str) -> str:
    for fragment, code in CODES:
        if fragment in message:
            return code
    raise AssertionError(f'no spec warning code covers {message!r}')  # pragma: no cover


@pytest.fixture(autouse=True)
def _record_warnings() -> Any:  # pyright: ignore[reportUnusedFunction]
    """Collect warnings rather than raising them, since half of every vector is what was warned."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        yield caught


def test_the_baseline_vectors(baseline_vectors: list[dict[str, Any]], _record_warnings: Any) -> None:
    caught: list[warnings.WarningMessage] = _record_warnings
    for vector in baseline_vectors:
        # Each vector is its own process as far as the once-per-process warning guard is concerned.
        reset_warned_messages()
        del caught[:]
        data: dict[str, Any] = vector['input']
        blocks = [
            Block(text=block['text'], id=block.get('id'), dynamic=block.get('dynamic', False))
            for block in data.get('blocks', [])
        ]
        tools = [
            ToolDef(
                name=tool['name'],
                description=tool.get('description'),
                parameters_json_schema=tool.get('parameters_json_schema', {}),
                toolset=tool.get('toolset'),
            )
            for tool in data.get('tools', [])
        ]
        baseline = build_baseline(
            instructions=blocks, model=data.get('model'), settings=data.get('settings'), tools=tools
        )
        assert baseline.model_dump(exclude_none=True) == vector['expected'], vector['name']
        assert [code_of(str(warning.message)) for warning in caught] == vector.get('warnings', []), vector['name']


def test_the_config_parsing_vectors(config_parsing_vectors: list[dict[str, Any]], _record_warnings: Any) -> None:
    caught: list[warnings.WarningMessage] = _record_warnings
    for vector in config_parsing_vectors:
        reset_warned_messages()
        del caught[:]
        config = AgentConfig.model_validate(expand_repeats(vector['input']))
        assert config.model_dump(exclude_none=True) == expand_repeats(vector['expected']), vector['name']
        assert [code_of(str(warning.message)) for warning in caught] == vector['warnings'], vector['name']
        if 'unrecognized_settings' in vector:
            assert config.settings is not None
            assert list(config.settings.unrecognized) == vector['unrecognized_settings'], vector['name']


CANONICAL_SPEC_SHA256 = 'f9fa69ee77a56d0eed2d7448cf42b4f0052645ec8d1ad38508d9a0bf5384d155'

SPEC_LOCKSTEP = (
    'The vectors in tests/agent_control/spec/ are one half of a contract with every other Agent '
    'Control SDK, and this repository holds the canonical copy: logfire-js vendors the same files '
    'and pins the same digest. If this assertion fails because you deliberately changed a rule, '
    'copy the whole directory into logfire-js, update the digest in both repositories to the value '
    'this test reports, and land the two changes together. If you did not mean to change a rule, '
    'the edit to spec/ is the bug.'
)


def spec_sha256() -> str:
    """A digest over every file in `spec/`, name and content, in a stable order.

    Line endings are normalized so a checkout that rewrites them still agrees with the digest the
    other SDK pins.
    """
    digest = hashlib.sha256()
    for path in sorted(SPEC.iterdir()):
        digest.update(path.name.encode())
        digest.update(b'\0')
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
        digest.update(b'\0')
    return digest.hexdigest()


def test_the_vectors_match_the_digest_every_copy_pins() -> None:
    assert spec_sha256() == CANONICAL_SPEC_SHA256, SPEC_LOCKSTEP
