"""Data models for the optimization SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

InputsT = TypeVar('InputsT')
OutputT = TypeVar('OutputT')
MetadataT = TypeVar('MetadataT')


@dataclass
class OptimizeIterationResult(Generic[InputsT, OutputT, MetadataT]):
    """Result of a single optimization iteration."""

    iteration_number: int
    iteration_id: str | None
    candidate_value: str
    status: Literal['rejected', 'accepted', 'applied', 'failed']
    baseline_scores: dict[str, float]
    candidate_scores: dict[str, float]
    score_delta: dict[str, float]
    agent_summary: str | None = None
    error: str | None = None


@dataclass
class OptimizeVariableResult(Generic[InputsT, OutputT, MetadataT]):
    """Result of a full optimization run."""

    optimization_id: str | None
    variable_name: str
    status: str
    baseline_value: str
    best_value: str
    primary_metric: str
    baseline_score: float | None
    best_score: float | None
    final_memory: str | None
    iterations: list[OptimizeIterationResult[InputsT, OutputT, MetadataT]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    applied_version: int | None = None
    applied_label: str | None = None
    dashboard_url: str | None = None


# API response types (matching backend TypedDicts)


@dataclass
class OptimizationInfo:
    """Optimization config as returned by the backend API."""

    id: str
    organization_id: str
    project_id: str
    variable_definition_id: str
    optimization_mode: str
    lifecycle_state: str
    active_iteration_id: str | None
    optimization_instructions: str
    optimization_memory: str | None
    model_config: dict[str, Any]
    trigger_config: dict[str, Any]
    control_label: str
    treatment_label: str
    require_approval: bool
    feedback_source: str


@dataclass
class IterationInfo:
    """Iteration as returned by the backend API."""

    id: str
    optimization_id: str
    iteration_number: int
    status: str
    proposed_value: str | None = None
    reasoning: str | None = None
    memory_update: str | None = None
    confidence: float | None = None
    control_metrics: dict[str, Any] | None = None
    treatment_metrics: dict[str, Any] | None = None
