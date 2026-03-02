"""Logfire variable optimization SDK.

Provides the `optimize_variable` and `optimize_variable_async` functions
for offline optimization loops that integrate with the Logfire backend.
"""

from logfire.optimization._loop import optimize_variable, optimize_variable_async
from logfire.optimization._models import OptimizeIterationResult, OptimizeVariableResult

__all__ = [
    'optimize_variable',
    'optimize_variable_async',
    'OptimizeIterationResult',
    'OptimizeVariableResult',
]
