import logfire

logfire.configure()
logfire.instrument_openai()
logfire.instrument_httpx(capture_all=True)
logfire.install_auto_tracing(modules=['gepa'], min_duration=0)

from gepa.api import optimize  # type: ignore  # noqa

from logfire._internal.utils import JsonDict  # noqa
from logfire.experimental._gepa._gepa import (  # noqa
    CombinedSimpleAdapterMixin,
    EvaluationInput,
    EvaluationResult,
    ManagedVarsEvaluateAdapterWrapper,
    ReflectionItem,
)

MyDataInst = str
MyTrajectory = str
MyRolloutOutput = int

prompt = logfire.var(name='prompt', default='Say 6', type=str)


class MyAdapter(
    CombinedSimpleAdapterMixin[MyDataInst, MyTrajectory, MyRolloutOutput],
):
    def evaluate_instance(self, eval_input: EvaluationInput[MyDataInst]):
        if '42' in prompt.get().value:
            output = 42
            score = 1
        else:
            output = 0
            score = 0
        return EvaluationResult(output=output, score=score, trajectory=eval_input.data)

    def reflect_item(self, item: ReflectionItem[MyTrajectory, MyRolloutOutput]) -> JsonDict:
        return {'question': item.trajectory, 'response': item.output, 'feedback': 'The answer should be 42.'}


adapter = ManagedVarsEvaluateAdapterWrapper(wrapped=MyAdapter())

seed_prompt = {'prompt': 'Say 0'}

gepa_result = optimize(  # type: ignore
    seed_candidate=seed_prompt,
    adapter=adapter,
    trainset=['What is the (numeric) answer to life, the universe and everything?'],
    reflection_lm='openai/gpt-4.1-mini',
    max_metric_calls=2,
)
