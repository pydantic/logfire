"""One resolution per run, reaching both hooks, and never shared between two runs at once."""

from __future__ import annotations

import asyncio
import gc
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from agents import Agent, ModelSettings, RunContextWrapper, Runner
from agents.models.interface import ModelTracing
from agents.retry import ModelRetryAdvice, ModelRetryAdviceRequest
from inline_snapshot import snapshot

from logfire.agent_control.openai_agents import agent_control
from logfire.agent_control.openai_agents._run import _current_runs  # pyright: ignore[reportPrivateUsage]
from logfire.variables import LabeledValue, Rollout as LabelRollout, VariableConfig
from logfire.variables.abstract import ResolvedVariable
from logfire.variables.local import LocalVariableProvider

from .conftest import (
    FakeModel,
    FakeProvider,
    controlled,
    get_weather,
    publish,
    text_output,
    tool_call,
    wait_for_baseline,
)

pytestmark = pytest.mark.anyio

ONE: dict[str, Any] = {
    'instructions': [{'id': 'agent', 'instructions': 'PROMPT ONE'}],
    'settings': {'temperature': 0.1},
}
TWO: dict[str, Any] = {
    'instructions': [{'id': 'agent', 'instructions': 'PROMPT TWO'}],
    'settings': {'temperature': 0.2},
}


class Rollout:
    """A project whose published value moves on between reads, as a rollout landing twice would.

    The whole point of resolving once is that a value cannot move *between* the prompt and the model
    request of one turn, and nothing but a value that changes on every read can tell the difference.
    """

    def __init__(self, *values: Mapping[str, Any]) -> None:
        self.values = values
        self.reads = 0

    def __call__(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        value = self.values[min(self.reads, len(self.values) - 1)]
        self.reads += 1
        return ResolvedVariable(
            name=variable_name,
            value=json.dumps(value),
            label='production',
            version=self.reads,
            reason='resolved',
        )


def rolling_out(
    project: LocalVariableProvider,
    monkeypatch: pytest.MonkeyPatch,
    *values: Mapping[str, Any],
    outputs: Sequence[Sequence[Any]] = (),
    **kwargs: Any,
) -> tuple[Agent[Any], FakeModel, Rollout]:
    """A managed agent whose config is republished between every read of it."""
    rollout = Rollout(*values)
    monkeypatch.setattr(project, 'get_serialized_value', rollout)
    inner = FakeModel(outputs=outputs)
    agent = agent_control(
        Agent(name='rolling', instructions='CODE PROMPT', tools=[get_weather], model='m'),
        provider=FakeProvider({'m': inner}),
        publish_baseline=False,
        **kwargs,
    )
    return agent, inner, rollout


async def test_the_prompt_and_the_request_apply_one_version(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two hooks, one read: the prompt cannot come from a version the settings did not."""
    agent, inner, rollout = rolling_out(project, monkeypatch, ONE, TWO)
    await Runner.run(agent, 'hello')

    assert rollout.reads == 1
    assert (inner.calls[0].system_instructions, inner.calls[0].model_settings.temperature) == ('PROMPT ONE', 0.1)


async def test_every_turn_of_a_run_applies_the_version_the_run_started_on(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publishing mid-run takes effect on the next run, not between two turns of this one."""
    agent, inner, rollout = rolling_out(
        project, monkeypatch, ONE, TWO, outputs=[[tool_call('get_weather')], [text_output('done')]]
    )
    await Runner.run(agent, 'weather?')

    assert rollout.reads == 1
    assert [call.system_instructions for call in inner.calls] == snapshot(['PROMPT ONE', 'PROMPT ONE'])
    assert {call.model_settings.temperature for call in inner.calls} == {0.1}


async def test_the_next_run_picks_up_what_was_published_since(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, inner, rollout = rolling_out(project, monkeypatch, ONE, TWO)
    await Runner.run(agent, 'hello')
    await Runner.run(agent, 'hello again')

    assert rollout.reads == 2
    assert [call.system_instructions for call in inner.calls] == snapshot(['PROMPT ONE', 'PROMPT TWO'])
    assert [call.model_settings.temperature for call in inner.calls] == snapshot([0.1, 0.2])


class Gate:
    """Holds every run that reaches it until they all have, so their resolutions really do interleave."""

    def __init__(self, parties: int) -> None:
        self.parties = parties
        self.arrived = 0
        self.open = asyncio.Event()

    async def wait(self) -> None:
        self.arrived += 1
        if self.arrived >= self.parties:
            self.open.set()
        await self.open.wait()


async def test_two_runs_at_once_each_keep_their_own_resolution(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both runs resolve before either reaches the model, and neither ends up with the other's value."""
    rollout = Rollout(ONE, TWO)
    monkeypatch.setattr(project, 'get_serialized_value', rollout)
    gate = Gate(2)
    inner = FakeModel()

    async def held(context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
        await gate.wait()
        return ''

    agent = agent_control(
        Agent(name='rolling', tools=[get_weather], model='m'),
        # A block that adds nothing and only waits, so both runs have rendered their prompt -- and so
        # resolved -- before either of them reaches the model.
        instructions={'agent': 'CODE PROMPT', 'gate': held},
        provider=FakeProvider({'m': inner}),
        publish_baseline=False,
    )
    await asyncio.gather(Runner.run(agent, 'first'), Runner.run(agent, 'second'))

    assert rollout.reads == 2
    assert sorted((call.system_instructions or '', call.model_settings.temperature) for call in inner.calls) == (
        snapshot([('PROMPT ONE', 0.1), ('PROMPT TWO', 0.2)])
    )


async def test_a_run_cleans_up_after_its_own_model_and_no_one_elses(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs on two published models: the runner tells the wrapper, the wrapper tells the right one."""
    cleaned: list[str] = []
    closed: list[str] = []

    class Lifecycle(FakeModel):
        async def _cleanup_on_run_end(self, owner: object) -> None:
            cleaned.append(self.label)

        async def close(self) -> None:
            closed.append(self.label)

    gate = Gate(2)
    code, first, second = Lifecycle('code'), Lifecycle('first'), Lifecycle('second')
    rollout = Rollout({'model': 'openai:first'}, {'model': 'openai:second'})
    monkeypatch.setattr(project, 'get_serialized_value', rollout)

    async def held(context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
        await gate.wait()
        return 'Hi.'

    provider = FakeProvider({'m': code, 'first': first, 'second': second})
    agent = agent_control(
        Agent(name='rolling', model='m'),
        instructions={'agent': held},
        provider=provider,
        publish_baseline=False,
    )
    await asyncio.gather(Runner.run(agent, 'first'), Runner.run(agent, 'second'))

    assert sorted(cleaned) == snapshot(['first', 'second'])
    # Every instance the wrapper resolved is closed with it, not only the one that answered last --
    # and the agent's own model is not among them, because every request here was served by a
    # published one and nothing ever asked the provider to build the model named in code.
    await controlled(agent).close()
    assert sorted(closed) == snapshot(['first', 'second'])


async def test_retry_advice_comes_from_the_model_this_run_used(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    advice = ModelRetryAdvice(retry_after=1.0)

    class Advising(FakeModel):
        def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
            return advice if self.label == 'second' else None

    seen: list[ModelRetryAdvice | None] = []

    async def record(context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
        model = agent.model
        assert model is not None and not isinstance(model, str)
        seen.append(model.get_retry_advice(_retry_request()))
        return 'Hi.'

    rollout = Rollout({'model': 'openai:first'}, {'model': 'openai:second'})
    monkeypatch.setattr(project, 'get_serialized_value', rollout)
    provider = FakeProvider({'m': Advising('code'), 'first': Advising('first'), 'second': Advising('second')})
    agent = agent_control(
        Agent(name='rolling', model='m'),
        instructions={'agent': record},
        provider=provider,
        publish_baseline=False,
    )
    await Runner.run(agent, 'first')
    await Runner.run(agent, 'second')

    # Asked before this run's first request, the run has no model to ask yet; after the second run's
    # request it is the second run's model that answers, not the first's.
    assert seen == snapshot([None, None])
    assert controlled(agent).get_retry_advice(_retry_request()) is advice


def _retry_request() -> ModelRetryAdviceRequest:
    return ModelRetryAdviceRequest(
        error=RuntimeError('boom'), attempt=1, stream=False, previous_response_id=None, conversation_id=None
    )


async def test_closing_reaches_the_model_the_agent_was_written_with(project: LocalVariableProvider) -> None:
    """An agent handed a `Model` object still has that object closed with the wrapper that stands in for it."""
    closed: list[str] = []

    class Closing(FakeModel):
        async def close(self) -> None:
            closed.append(self.label)

    inner = Closing('own')
    agent = agent_control(Agent(name='owning', instructions='Hi.', model=inner), publish_baseline=False)
    await Runner.run(agent, 'hello')
    await controlled(agent).close()

    assert closed == ['own']


async def test_an_agent_whose_model_was_replaced_is_left_alone(project: LocalVariableProvider) -> None:
    """The seam is on the agent, but it only speaks for a managed model: cloning one away disarms it."""
    inner = FakeModel('own')
    agent = agent_control(Agent(name='rolling', instructions='Hi.', model='m'), provider=FakeProvider())
    plain = agent.clone(model=inner, model_settings=ModelSettings())
    result = await Runner.run(plain, 'hello')

    assert result.final_output == 'done by own'


async def test_the_model_wrapper_resolves_for_itself_outside_a_run(project: LocalVariableProvider) -> None:
    """Called as a plain `Model`, with no run to have resolved for it, it still applies what is published."""
    publish(project, 'agent__standalone', {'settings': {'temperature': 0.4}})
    inner = FakeModel()
    agent = agent_control(
        Agent(name='standalone', instructions='Hi.', model='m'),
        provider=FakeProvider({'m': inner}),
        publish_baseline=False,
    )
    await controlled(agent).get_response(
        'Hi.',
        'hello',
        ModelSettings(),
        [],
        None,
        [],
        ModelTracing.DISABLED,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    )

    assert inner.calls[0].model_settings.temperature == 0.4


async def test_a_handoff_applies_the_next_agents_own_config(project: LocalVariableProvider) -> None:
    """Two managed agents in one run: each turn applies the config of the agent taking that turn."""
    publish(project, 'agent__front_desk', {'instructions': [{'id': 'agent', 'instructions': 'FRONT DESK'}]})
    publish(project, 'agent__specialist', {'instructions': [{'id': 'agent', 'instructions': 'SPECIALIST'}]})
    inner = FakeModel(
        outputs=[
            [tool_call('transfer_to_specialist', arguments='{}', call_id='call-handoff')],
            [text_output('handled')],
        ]
    )
    provider = FakeProvider({'m': inner})
    specialist = agent_control(Agent(name='specialist', instructions='I specialise.', model='m'), provider=provider)
    front_desk = agent_control(
        Agent(name='front_desk', instructions='I greet.', model='m', handoffs=[specialist]), provider=provider
    )
    result = await Runner.run(front_desk, 'help')

    assert [call.system_instructions for call in inner.calls] == snapshot(['FRONT DESK', 'SPECIALIST'])
    assert result.final_output == 'handled'


async def test_two_wrappers_of_one_config_keep_their_own_labels_in_one_run(
    project: LocalVariableProvider,
) -> None:
    """Wrapping an agent again for another label is what `label` is for, including within one run.

    Both wrappers read the same variable, and a handoff runs both of them under one
    `RunContextWrapper` -- so a run record keyed on the variable would hand the second wrapper the
    first one's resolution, and the second agent would send the first label's prompt under its own
    name. The record is keyed on the `AgentControl` instead, which is one per wrapping.
    """
    project.create_variable(
        VariableConfig(
            name='agent__two_labels',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps({'instructions': [{'id': 'agent', 'instructions': 'STABLE'}]}),
                ),
                'canary': LabeledValue(
                    version=2,
                    serialized_value=json.dumps({'instructions': [{'id': 'agent', 'instructions': 'NEW'}]}),
                ),
            },
            rollout=LabelRollout(labels={'production': 1.0}),
            overrides=[],
        )
    )
    inner = FakeModel(
        outputs=[[tool_call('transfer_to_two_labels', arguments='{}', call_id='call-handoff')], [text_output('done')]]
    )
    models = FakeProvider({'m': inner})
    code = Agent(name='two_labels', instructions='As written.', model='m')
    canary = agent_control(code, label='canary', provider=models, publish_baseline=False)
    stable = agent_control(
        Agent(name='two_labels', instructions='As written.', model='m', handoffs=[canary]),
        label='production',
        provider=models,
        publish_baseline=False,
    )

    await Runner.run(stable, 'help')

    assert [call.system_instructions for call in inner.calls] == snapshot(['STABLE', 'NEW'])


async def test_one_model_under_two_names_is_closed_once(project: LocalVariableProvider) -> None:
    """The resolved-model cache is keyed by the name asked for, and two names can be one object.

    `MultiProvider` answers a bare OpenAI name and its `openai/` spelling with the same model, so
    closing everything in the cache would release that one object's client twice.
    """
    closed: list[str] = []

    class Lifecycle(FakeModel):
        async def close(self) -> None:
            closed.append(self.label)

    one = Lifecycle('one')
    publish(project, 'agent__aliased', {'model': 'openai:alias'})
    agent = agent_control(
        # The baseline describes the model the *code* runs on, so this request resolves both names:
        # `alias`, which serves it, and `m`, which the editor is told about.
        Agent(name='aliased', instructions='Hi.', model='m'),
        label='production',
        provider=FakeProvider({'m': one, 'alias': one}),
    )
    wrapper = controlled(agent)
    await Runner.run(agent, 'hello')
    wait_for_baseline(agent)

    assert set(wrapper._resolved) == {'alias', 'm'}  # pyright: ignore[reportPrivateUsage]
    await wrapper.close()
    assert closed == snapshot(['one'])


async def test_a_run_stops_being_remembered_once_nothing_can_ask_about_it(
    project: LocalVariableProvider,
) -> None:
    """A record outlives its run, but not the last thing that could still ask about that run.

    Nothing else removes one, because the runner makes lifecycle calls after a run has ended and they
    have to find it. A task that wraps a fresh agent per request -- which the docs ask you not to do
    and nothing prevents -- would otherwise accumulate a record, and its models, for as long as it
    lives.
    """

    async def run_a_fresh_wrapper() -> None:
        agent = agent_control(
            Agent(name='ephemeral', instructions='Hi.', model='m'),
            provider=FakeProvider({'m': FakeModel()}),
            publish_baseline=False,
        )
        await Runner.run(agent, 'hello')

    await run_a_fresh_wrapper()
    await run_a_fresh_wrapper()
    gc.collect()
    await run_a_fresh_wrapper()

    # Three wrappers, three runs, one record: the two whose `RunResult` went out of scope with the
    # call that made it are gone, and the one belonging to the run that just ended is not.
    assert len(_current_runs.get()) == snapshot(1)
