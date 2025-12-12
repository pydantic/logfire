from __future__ import annotations

import functools
import inspect
import uuid
from typing import Any, Union, get_args, get_origin

from surrealdb.connections.async_template import AsyncTemplate
from surrealdb.connections.sync_template import SyncTemplate
from surrealdb.data.types.record_id import RecordIdType
from surrealdb.data.types.table import Table
from surrealdb.types import Value

from logfire._internal.main import Logfire


def is_complex_type(tp: type | type[Value]) -> bool:
    origin = get_origin(tp)
    if origin in {list, dict, set, tuple}:
        return True
    if tp in {Value}:
        return True
    if tp in (str, bool, int, float, type(None), uuid.UUID, Table, RecordIdType):
        return False
    if origin is Union:
        args = get_args(tp)
        return any(is_complex_type(arg) for arg in args)
    return True


def get_all_subclasses(cls: type) -> set[type]:
    subclasses: set[type] = set()
    for subclass in cls.__subclasses__():
        subclasses.add(subclass)
        subclasses.update(get_all_subclasses(subclass))
    return subclasses


def get_all_surrealdb_classes() -> set[type]:
    return get_all_subclasses(SyncTemplate) | get_all_subclasses(AsyncTemplate)


def instrument_surrealdb(obj: Any, logfire_instance: Logfire):
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='surrealdb')
    if obj is None:
        for cls in get_all_surrealdb_classes():
            instrument_surrealdb(cls, logfire_instance)
        return

    # TODO check that the templates have the same methods
    for name, template_method in inspect.getmembers(SyncTemplate):
        if not (
            inspect.isfunction(template_method)
            and not name.startswith('_')
            and SyncTemplate.__dict__.get(name) == template_method
        ):
            continue
        patch_method(obj, name, logfire_instance)


def patch_method(obj: Any, method_name: str, logfire_instance: Logfire):
    if hasattr(getattr(obj, method_name), '_logfire_template'):
        return  # already patched

    original_method = getattr(obj, method_name)
    sig = inspect.signature(original_method)
    template_params: list[str] = []
    scrubber = logfire_instance.config.scrubber
    for param_name, param in sig.parameters.items():
        if param_name == 'self':
            continue
        assert param.annotation is not inspect.Parameter.empty
        _, scrubbed = scrubber.scrub_value(path=(param_name,), value=None)
        if not is_complex_type(param.annotation) and not scrubbed:
            template_params.append(param_name)
    template = span_name = f'surrealdb {method_name}'
    if len(template_params) == 1:
        template += f' {{{template_params[0]}}}'
    elif len(template_params) > 1:
        template += ' ' + ', '.join(f'{p} = {{{p}}}' for p in template_params)

    def get_params(*args: Any, **kwargs: Any) -> dict[str, Any]:
        bound = sig.bind(*args, **kwargs)
        params = bound.arguments
        params.pop('self', None)
        return params

    if inspect.isgeneratorfunction(original_method):

        @functools.wraps(original_method)
        def wrapped_method(*args: Any, **kwargs: Any) -> Any:
            logfire_instance.info(template, **get_params(*args, **kwargs))
            return original_method(*args, **kwargs)
    else:

        @functools.wraps(original_method)
        def wrapped_method(*args: Any, **kwargs: Any) -> Any:
            with logfire_instance.span(template, **get_params(*args, **kwargs), _span_name=span_name):
                return original_method(*args, **kwargs)

    wrapped_method._logfire_template = template  # type: ignore

    setattr(obj, method_name, wrapped_method)
