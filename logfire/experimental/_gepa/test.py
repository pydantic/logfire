from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import logfire
from logfire._internal.utils import JsonDict

logfire.install_auto_tracing(modules=['gepa'], min_duration=0)

from logfire.experimental._gepa._gepa import (  # noqa
    CombinedSimpleAdapterMixin,
    EvaluationInput,
    EvaluationResult,
    ManagedVarsEvaluateAdapterWrapper,
    ReflectionItem,
)

from gepa.api import optimize  # type: ignore  # noqa

logfire.configure()
logfire.instrument_openai()
logfire.instrument_httpx(capture_all=True)

MyDataInst = str
MyTrajectory = str
MyRolloutOutput = int

prompt = logfire.var(name='prompt', default='Say 6', type=str)


class MyAdapter(CombinedSimpleAdapterMixin[MyDataInst, MyTrajectory, MyRolloutOutput]):
    def propose_new_texts_impl(
        self,
        candidate: dict[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        assert list(candidate.keys()) == list(reflective_dataset.keys()) == components_to_update == ['prompt']
        # In practice this should construct a prompt to an LLM,
        # which asks the LLM to suggest a new prompt.
        # It would help for the user to provide a description of the problem/task/goal,
        # (although this becomes redundant when the agent system instructions are present,
        # which presumably describe the task already)
        # and maybe descriptions of each variable.
        return {'prompt': f'Say {reflective_dataset["prompt"][0]["expected output"]}'}

    def evaluate_instance(self, eval_input: EvaluationInput[MyDataInst]):
        # In practice this would run some task function on eval_input.data.
        # Also, if eval_input.capture_traces is True, it should create a trajectory containing:
        # - the inputs (eval_input.data)
        # - traces/spans captured during execution

        # The value of `prompt` is set by the outer ManagedVarsEvaluateAdapterWrapper.
        if '42' in prompt.get().value:
            output = 42
            score = 1
        else:
            output = 0
            score = 0
        return EvaluationResult(output=output, score=score, trajectory=eval_input.data)

    def reflect_item(self, item: ReflectionItem[MyTrajectory, MyRolloutOutput]) -> JsonDict:
        # This is where you'd run evaluators to provide feedback on the trajectory/output.
        # You might also filter the traces/spans to only include parts where
        # the managed variable corresponding to item.component was used/set.
        return {'question': item.trajectory, 'response': item.output, 'expected output': 42}


adapter = ManagedVarsEvaluateAdapterWrapper(wrapped=MyAdapter())

seed_prompt = {var.name: var.get().value for var in [prompt]}

gepa_result = optimize(  # type: ignore
    seed_candidate=seed_prompt,
    adapter=adapter,
    trainset=['What is the (numeric) answer to life, the universe and everything?'],
    max_metric_calls=2,
)

print(gepa_result)  # type: ignore
assert gepa_result.best_candidate == {'prompt': 'Say 42'}
