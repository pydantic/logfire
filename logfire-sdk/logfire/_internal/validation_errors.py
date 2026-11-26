from __future__ import annotations

from typing import Any, LiteralString, cast, get_args

from pydantic import ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError, core_schema

from .scrubbing import BaseScrubber, JsonPath

_BUILTIN_ERROR_TYPES = frozenset(get_args(core_schema.ErrorType))


def scrubbed_validation_error(exc: ValidationError, scrubber: BaseScrubber, path: JsonPath) -> ValidationError | None:
    """Rebuild a validation error so its rendered text uses scrubbed inputs."""
    try:
        original_errors = cast('list[dict[str, Any]]', exc.errors(include_url=False))
        scrubbed, _ = scrubber.scrub_value(path, original_errors)
        if not isinstance(scrubbed, list):
            return None
        errors = cast('list[dict[str, Any]]', scrubbed)
        if not any(original.get('input') != changed.get('input') for original, changed in zip(original_errors, errors)):
            return None

        line_errors: list[dict[str, Any]] = []
        for original, changed in zip(original_errors, errors):
            error = dict(changed)
            if (
                error['type'] not in _BUILTIN_ERROR_TYPES
                or error.get('msg') != original.get('msg')
                or error.get('ctx') != original.get('ctx')
            ):
                # The rebuilt error is used only for rendered text. The original error
                # still supplies structured data, so avoid interpolating context again.
                error['type'] = PydanticCustomError(
                    cast(LiteralString, str(error['type'])), cast(LiteralString, str(error['msg']))
                )
            line_errors.append(error)

        hide_input = 'input_value=' not in str(exc) and any('input' in error for error in original_errors)
        rebuilt = ValidationError.from_exception_data(
            exc.title, cast('list[InitErrorDetails]', line_errors), hide_input=hide_input
        )
        rebuilt.__traceback__ = exc.__traceback__
        rebuilt.__cause__ = exc.__cause__
        rebuilt.__context__ = exc.__context__
        rebuilt.__suppress_context__ = exc.__suppress_context__
        if hasattr(exc, '__notes__'):
            rebuilt.__notes__ = exc.__notes__.copy()
        return rebuilt
    except Exception:
        # A custom error or an older Pydantic version may reject rebuilding.
        return None


def replace_validation_errors(exc: BaseException, scrubber: BaseScrubber, path: JsonPath) -> BaseException:
    """Return a scrubbed copy of an exception chain without changing application exceptions."""
    seen: set[int] = set()

    def replace(current: BaseException) -> BaseException:
        if id(current) in seen:
            return current
        seen.add(id(current))

        cause = replace(current.__cause__) if current.__cause__ is not None else None
        context = replace(current.__context__) if current.__context__ is not None else None
        group = cast('BaseExceptionGroup[BaseException]', current) if isinstance(current, BaseExceptionGroup) else None
        children = tuple(replace(child) for child in group.exceptions) if group is not None else None
        changed = (
            cause is not current.__cause__
            or context is not current.__context__
            or (
                children is not None
                and group is not None
                and any(new is not old for new, old in zip(children, group.exceptions))
            )
        )
        rebuilt = scrubbed_validation_error(current, scrubber, path) if isinstance(current, ValidationError) else None
        base_current = cast(BaseException, current)
        if rebuilt is not None:
            changed = True
        if not changed:
            return base_current

        try:
            if rebuilt is not None:
                clone: BaseException = rebuilt
            elif children is not None and group is not None:
                clone = group.derive(children)
            else:
                clone = BaseException.__new__(type(base_current), *base_current.args)
            clone.__dict__.update(base_current.__dict__)
            if rebuilt is None:
                clone.args = base_current.args
            clone.__traceback__ = base_current.__traceback__
            clone.__cause__ = cause
            clone.__context__ = context
            clone.__suppress_context__ = base_current.__suppress_context__
            if hasattr(base_current, '__notes__'):
                clone.__notes__ = base_current.__notes__.copy()
            return clone
        except Exception:
            return base_current

    return replace(exc)
