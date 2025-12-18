from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Generic

from gepa.core.adapter import DataInst, EvaluationBatch, GEPAAdapter, RolloutOutput, Trajectory

import logfire
from logfire._internal.utils import JsonDict


@dataclass
class ReflectionItem(Generic[Trajectory, RolloutOutput]):
    candidate: dict[str, str]
    component: str
    trajectory: Trajectory
    score: float
    output: RolloutOutput


class SimpleReflectionAdapterMixin(GEPAAdapter[DataInst, Trajectory, RolloutOutput], ABC):
    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[Trajectory, RolloutOutput],
        components_to_update: list[str],
    ):
        assert len(components_to_update) == 1
        component = components_to_update[0]

        assert eval_batch.trajectories, 'Trajectories are required to build a reflective dataset.'

        return {
            component: [
                self.reflect_item(ReflectionItem(candidate, component, *inst))
                for inst in zip(eval_batch.trajectories, eval_batch.scores, eval_batch.outputs, strict=True)
            ]
        }

    @abstractmethod
    def reflect_item(self, item: ReflectionItem[Trajectory, RolloutOutput]) -> JsonDict: ...


@dataclass
class EvaluationInput(Generic[DataInst]):
    data: DataInst
    candidate: dict[str, str]
    capture_traces: bool


@dataclass
class EvaluationResult(Generic[Trajectory, RolloutOutput]):
    output: RolloutOutput
    score: float
    trajectory: Trajectory | None = None


class SimpleEvaluateAdapterMixin(GEPAAdapter[DataInst, Trajectory, RolloutOutput], ABC):
    def evaluate(
        self,
        batch: list[DataInst],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ):
        outputs: list[RolloutOutput] = []
        scores: list[float] = []
        trajectories: list[Trajectory] | None = [] if capture_traces else None

        for data in batch:
            eval_input = EvaluationInput(data=data, candidate=candidate, capture_traces=capture_traces)
            eval_result = self.evaluate_instance(eval_input)
            outputs.append(eval_result.output)
            scores.append(eval_result.score)

            if trajectories is not None:
                assert eval_result.trajectory
                trajectories.append(eval_result.trajectory)

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    @abstractmethod
    def evaluate_instance(
        self, eval_input: EvaluationInput[DataInst]
    ) -> EvaluationResult[Trajectory, RolloutOutput]: ...


class ManagedVarsEvaluateAdapterMixin(SimpleEvaluateAdapterMixin[DataInst, Trajectory, RolloutOutput], ABC):
    def evaluate(
        self,
        batch: list[DataInst],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ):
        stack = ExitStack()
        variables = logfire.get_variables()
        with stack:
            for var in variables:
                if var.name in candidate:
                    stack.enter_context(var.override(candidate[var.name]))
            return super().evaluate(batch, candidate, capture_traces)
