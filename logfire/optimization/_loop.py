"""The offline optimization loop.

Implements `optimize_variable_async` and `optimize_variable` which coordinate:
1. Creating an optimization record on the backend
2. Evaluating the baseline
3. Requesting proposals from the worker agent
4. Evaluating candidates locally
5. Accepting or rejecting based on score improvement
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, TypeVar

import logfire

from logfire.optimization._client import AsyncOptimizationClient, OptimizationApiError
from logfire.optimization._models import OptimizeIterationResult, OptimizeVariableResult

if TYPE_CHECKING:
    from logfire.variables.variable import Variable
    from pydantic_evals import Dataset

InputsT = TypeVar('InputsT')
OutputT = TypeVar('OutputT')
MetadataT = TypeVar('MetadataT')

_TERMINAL_STATUSES = {'promoted', 'rolled_back', 'rejected', 'failed', 'timed_out', 'canceled'}
_PROPOSAL_READY = {'proposed', 'awaiting_approval'}


async def optimize_variable_async(
    variable: Variable[str],
    dataset: Dataset[InputsT, OutputT, MetadataT],
    task: Callable[..., Any],
    objective: str,
    *,
    max_iterations: int = 10,
    min_improvement: float = 0.0,
    evaluators: Any = None,
    report_evaluators: Any = None,
    apply_candidate: Callable[[str], AbstractContextManager[None]] | None = None,
    auto_deploy: bool = False,
    deployment_label: str = 'production',
    use_trace_investigation: bool = False,
    read_token: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> OptimizeVariableResult[InputsT, OutputT, MetadataT]:
    """Run an offline optimization loop for a managed variable.

    This function coordinates with the Logfire backend to iteratively
    improve a variable value using the optimization agent.

    Args:
        variable: The Logfire Variable to optimize.
        dataset: A pydantic-evals Dataset to evaluate against.
        task: The task function to evaluate. Called as task(inputs) for each case.
        objective: Natural language description of what to optimize for.
        max_iterations: Maximum number of optimization iterations.
        min_improvement: Minimum score improvement to accept a proposal.
        evaluators: Override dataset evaluators for this run.
        report_evaluators: Override dataset report evaluators for this run.
        apply_candidate: Custom injection function. If None, uses variable.override().
        auto_deploy: If True, automatically deploy accepted proposals.
        deployment_label: Which label to deploy to (default 'production').
        use_trace_investigation: Enable trace investigation (requires read token).
        read_token: Read token for trace investigation.
        api_key: Logfire API key. If not provided, uses the variable's logfire instance.
        base_url: Logfire API base URL. If not provided, inferred from API key.
        model: Model name for the optimization agent (e.g. 'openai:gpt-4o'). Required.

    Returns:
        OptimizeVariableResult with the outcome and iteration history.
    """
    if api_key is None:
        # Try to get from the variable's logfire instance
        config = variable.logfire_instance._config  # pyright: ignore[reportPrivateUsage]
        api_key = config.token
        if api_key is None:
            raise ValueError('api_key must be provided or the variable must be connected to a Logfire instance')

    # Capture baseline value before starting
    baseline_value = variable.get().value

    async with AsyncOptimizationClient(api_key=api_key, base_url=base_url) as client:
        # 1. Create optimization record
        create_data: dict[str, Any] = {
            'variable_name': variable.name,
            'optimization_mode': 'offline',
            'optimization_instructions': objective,
            'feedback_source': 'eval_dataset',
            'trigger_config': {'kind': 'manual'},
            'require_approval': not auto_deploy,
        }
        if model is not None:
            create_data['model_config'] = {'model': model}
        try:
            optimization_data = await client.create_optimization(create_data)
        except OptimizationApiError as exc:
            if exc.status_code == 409:
                # Optimization already exists — delete it and recreate
                logfire.info('Optimization already exists for variable {name}, recreating...', name=variable.name)
                # We need to find the existing optimization ID. The error means
                # one already exists for this variable. List all and find it.
                # For now, try getting it by listing, or just get the optimization by variable name
                # Since there's no list-by-name endpoint, let's get the optimization from the
                # create response or use the variable name endpoint
                existing = await client.get_optimization_by_variable_name(variable.name)
                if existing:
                    await client.delete_optimization(existing['id'])
                optimization_data = await client.create_optimization(create_data)
            else:
                raise
        optimization_id = optimization_data['id']

        # 2. Evaluate baseline
        with logfire.span('evaluating baseline'):
            baseline_report = await dataset.evaluate(task)
        baseline_scores = _extract_scores(baseline_report)

        # Build a rich evaluation context string for the worker agent
        evaluation_context = _build_evaluation_context(baseline_report, baseline_scores, objective)

        best_value = baseline_value
        best_scores = baseline_scores
        iterations: list[OptimizeIterationResult[InputsT, OutputT, MetadataT]] = []

        # 3. Iteration loop
        for i in range(max_iterations):
            with logfire.span('optimization iteration {iteration}', iteration=i + 1):
                iter_result = await _run_single_iteration(
                    client=client,
                    optimization_id=optimization_id,
                    variable=variable,
                    dataset=dataset,
                    task=task,
                    baseline_scores=baseline_scores,
                    best_scores=best_scores,
                    min_improvement=min_improvement,
                    apply_candidate=apply_candidate,
                    auto_deploy=auto_deploy,
                    evaluators=evaluators,
                    report_evaluators=report_evaluators,
                    evaluation_context=evaluation_context,
                )
                iterations.append(iter_result)

                if iter_result.status == 'accepted' or iter_result.status == 'applied':
                    best_value = iter_result.candidate_value
                    best_scores = iter_result.candidate_scores

                if iter_result.status == 'failed':
                    logfire.warn(
                        'Optimization iteration {iteration} failed: {error}',
                        iteration=i + 1,
                        error=iter_result.error,
                    )

        # 4. Build result
        primary_metric = next(iter(baseline_scores), '')
        return OptimizeVariableResult(
            optimization_id=optimization_id,
            variable_name=variable.name,
            status='completed',
            baseline_value=baseline_value,
            best_value=best_value,
            primary_metric=primary_metric,
            baseline_score=baseline_scores.get(primary_metric),
            best_score=best_scores.get(primary_metric),
            final_memory=None,
            iterations=iterations,
        )


async def _run_single_iteration(
    *,
    client: AsyncOptimizationClient,
    optimization_id: str,
    variable: Variable[str],
    dataset: Dataset[Any, Any, Any],
    task: Callable[..., Any],
    baseline_scores: dict[str, float],
    best_scores: dict[str, float],
    min_improvement: float,
    apply_candidate: Callable[[str], AbstractContextManager[None]] | None,
    auto_deploy: bool,
    evaluators: Any,
    report_evaluators: Any,
    evaluation_context: str | None = None,
) -> OptimizeIterationResult[Any, Any, Any]:
    """Execute a single iteration of the optimization loop."""
    try:
        # Build context for the worker agent
        context: dict[str, Any] | None = None
        if baseline_scores or best_scores or evaluation_context:
            context = {
                'baseline_scores': baseline_scores,
                'best_scores': best_scores,
            }
            if evaluation_context:
                context['details'] = evaluation_context

        # Request proposal from worker
        iteration_data = await client.request_proposal(optimization_id, context=context)
        iteration_id = iteration_data['id']
        iteration_number = iteration_data['iteration_number']

        # Poll until proposal is ready
        iteration_data = await client.poll_iteration(
            optimization_id,
            iteration_id,
            target_status=_PROPOSAL_READY | _TERMINAL_STATUSES,
            timeout=600.0,
        )

        if iteration_data['status'] in _TERMINAL_STATUSES:
            return OptimizeIterationResult(
                iteration_number=iteration_number,
                iteration_id=iteration_id,
                candidate_value='',
                status='failed',
                baseline_scores=baseline_scores,
                candidate_scores={},
                score_delta={},
                agent_summary=iteration_data.get('reasoning'),
                error=f'Iteration ended with status: {iteration_data["status"]}',
            )

        proposed_value = iteration_data['proposed_value']
        reasoning = iteration_data.get('reasoning')

        # Evaluate candidate locally
        with logfire.span('evaluating candidate'):
            if apply_candidate is not None:
                with apply_candidate(proposed_value):
                    candidate_report = await dataset.evaluate(task)
            else:
                with variable.override(proposed_value):
                    candidate_report = await dataset.evaluate(task)

        candidate_scores = _extract_scores(candidate_report)

        # Submit evaluation to backend
        await client.submit_evaluation(
            optimization_id,
            iteration_id,
            control_metrics=baseline_scores,
            treatment_metrics=candidate_scores,
        )

        # Compare scores
        score_delta = {
            k: candidate_scores.get(k, 0) - baseline_scores.get(k, 0) for k in set(baseline_scores) | set(candidate_scores)
        }

        # Check if improved
        primary_metric = next(iter(baseline_scores), '')
        improved = (
            primary_metric in candidate_scores
            and candidate_scores[primary_metric] - best_scores.get(primary_metric, 0) >= min_improvement
        )

        if improved:
            # Always approve on the backend to clear the active iteration,
            # allowing subsequent iterations to proceed.
            await client.approve(optimization_id)
            status = 'applied' if auto_deploy else 'accepted'
        else:
            await client.reject(optimization_id, reason='Score did not improve sufficiently')
            status = 'rejected'

        return OptimizeIterationResult(
            iteration_number=iteration_number,
            iteration_id=iteration_id,
            candidate_value=proposed_value,
            status=status,
            baseline_scores=baseline_scores,
            candidate_scores=candidate_scores,
            score_delta=score_delta,
            agent_summary=reasoning,
        )

    except Exception as exc:
        return OptimizeIterationResult(
            iteration_number=0,
            iteration_id=None,
            candidate_value='',
            status='failed',
            baseline_scores=baseline_scores,
            candidate_scores={},
            score_delta={},
            error=str(exc),
        )


def _extract_scores(report: Any) -> dict[str, float]:
    """Extract numeric scores from a pydantic-evals evaluation report."""
    scores: dict[str, float] = {}
    if hasattr(report, 'averages'):
        averages = report.averages()
        if averages is not None and hasattr(averages, 'scores'):
            for name, value in averages.scores.items():
                if isinstance(value, (int, float)):
                    scores[name] = float(value)
    return scores


def _build_evaluation_context(report: Any, scores: dict[str, float], objective: str) -> str:
    """Build a rich evaluation context string for the worker agent.

    Includes aggregate scores, per-case details, and the optimization objective
    so the worker agent has full context for making targeted proposals.
    """
    parts: list[str] = []

    # Aggregate scores
    if scores:
        score_lines = ', '.join(f'{k}: {v}' for k, v in scores.items())
        parts.append(f'Aggregate scores: {score_lines}')

    # Per-case details if available
    if hasattr(report, 'cases'):
        for case_result in report.cases:
            case_name = getattr(case_result, 'name', '?')
            case_scores = {}
            if hasattr(case_result, 'scores') and case_result.scores:
                for name, value in case_result.scores.items():
                    if isinstance(value, (int, float)):
                        case_scores[name] = value
            case_metrics = {}
            if hasattr(case_result, 'metrics') and case_result.metrics:
                for name, value in case_result.metrics.items():
                    if isinstance(value, (int, float)):
                        case_metrics[name] = value
            if case_scores:
                parts.append(f'Case "{case_name}" scores: {case_scores}')
            if case_metrics:
                parts.append(f'Case "{case_name}" metrics: {case_metrics}')

    # Include the objective
    if objective:
        parts.append(f'Optimization objective: {objective}')

    return '\n'.join(parts)


def optimize_variable(
    variable: Variable[str],
    dataset: Dataset[InputsT, OutputT, MetadataT],
    task: Callable[..., Any],
    objective: str,
    **kwargs: Any,
) -> OptimizeVariableResult[InputsT, OutputT, MetadataT]:
    """Synchronous wrapper for optimize_variable_async.

    See optimize_variable_async for full documentation.
    """
    return asyncio.run(
        optimize_variable_async(
            variable=variable,
            dataset=dataset,
            task=task,
            objective=objective,
            **kwargs,
        )
    )
