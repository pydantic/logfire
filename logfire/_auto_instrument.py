from __future__ import annotations

import importlib
import inspect
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any, ContextManager, Literal

from typing_extensions import TypedDict

from logfire._main import Logfire, LogfireSpan

if TYPE_CHECKING:
    from _typeshed import ProfileFunction


_SPANS: dict[tuple[FrameType, str], ContextManager[LogfireSpan]] = {}


class ExtractedMetadata(TypedDict):
    namespace: str | None
    function: str
    filepath: str
    lineno: int


def extract_attributes(event: Literal['call', 'c_call'], frame: FrameType, arg: Any) -> ExtractedMetadata:
    if event == 'call':
        module = inspect.getmodule(frame)
        module_name = module.__name__ if module else None
        f_name = getattr(frame.f_code, 'co_qualname', frame.f_code.co_name)
        assert frame.f_back is not None
        return ExtractedMetadata(
            namespace=module_name,
            function=f_name,
            filepath=frame.f_back.f_code.co_filename,
            lineno=frame.f_back.f_lineno,
        )
    else:
        assert event == 'c_call'
        if arg.__module__:
            module = inspect.getmodule(arg)
            if module:
                module_name = module.__name__
            else:
                module_name = None
        else:
            module_name = arg.__module__
        f_name = getattr(arg, '__qualname__', arg.__name__)
        return ExtractedMetadata(
            namespace=module_name,
            function=f_name,
            filepath=frame.f_code.co_filename,
            lineno=frame.f_lineno,
        )


@dataclass
class FuncTracer:
    logfire: Logfire
    modules: re.Pattern[str] | None = None
    previous_tracer: ProfileFunction | None = None

    def __call__(
        self,
        frame: FrameType,
        event: str,
        arg: Any,
    ) -> None:
        if self.previous_tracer is not None:
            self.previous_tracer(frame, event, arg)
        if self.modules is not None:
            if event == 'c_call':
                # always filter out c calls, we have no way to get the filename
                return
            if not self.modules.search(frame.f_code.co_filename):
                return
        # skip if we are within ourselves because we call functions in here that we don't want to trace
        f = frame
        while f:
            if (
                f.f_code.co_name == FuncTracer.__call__.__name__
                and f.f_code.co_filename == FuncTracer.__call__.__code__.co_filename
            ):
                return
            f = f.f_back
        if event == 'call' or event == 'c_call':
            metadata = extract_attributes(event, frame, arg)
            name = f'{metadata["namespace"]}.{metadata["function"]}' if metadata['namespace'] else metadata['function']
            attributes = {
                'code.function': metadata['function'],
                'code.lineno': metadata['lineno'],
                'code.filepath': metadata['filepath'],
            }
            if metadata['namespace'] is not None:
                attributes['code.namespace'] = metadata['namespace']
            logfire_span_gen = self.logfire.span(
                'function {function_name}() called',
                span_name=name,
                **attributes,
                function_name=metadata['function'],
            )
            logfire_span_gen.__enter__()
            _SPANS[(frame, 'call')] = logfire_span_gen
        elif event == 'return' or event == 'c_return':
            f = frame
            while f:
                logfire_span: ContextManager[LogfireSpan] | None = _SPANS.pop((f, 'call'), None)
                if logfire_span is not None:
                    logfire_span.__exit__(None, None, None)
                    break
                f = f.f_back


def get_module_path(module: str) -> str:
    try:
        path = Path(inspect.getfile(importlib.import_module(module)))
    except (KeyError, TypeError):
        # maybe we are currently defining the module
        # traverse up the stack to see if we can find it
        for frame in inspect.stack():
            mod = inspect.getmodule(frame[0])
            if mod and mod.__name__.startswith(module):
                path = Path(inspect.getfile(frame[0])).parent
                break
        raise KeyError(f'module {module} not found')
    # match either that path or any subpath
    if path.stem == '__init__':
        path = path.parent
        return f'^{path}/.*$'
    return f'^{path}$'


def install_automatic_instrumentation(modules: list[str] | None = None, logfire: Logfire | None = None) -> None:
    """Install automatic instrumentation.

    Automatic instrumentation will trace all function calls in the modules specified by the modules argument.

    Calling this function multiple times will overwrite the previous modules.

    Args:
        modules: List of module names to trace. Defaults to None.
    """
    # if modules is None then use the filename of the module of the caller
    # otherwise get the filenames for each module and join them with |
    if modules is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        if module is None:
            raise KeyError('module not found')
        modules_pattern = get_module_path(module.__name__.split('.')[0])
    else:
        modules_pattern = '|'.join([get_module_path(module) for module in modules])
    if logfire is None:
        from logfire import DEFAULT_LOGFIRE_INSTANCE

        logfire = DEFAULT_LOGFIRE_INSTANCE
    tracer = FuncTracer(
        logfire=logfire,
        modules=re.compile(modules_pattern),
        previous_tracer=sys.getprofile(),
    )
    sys.setprofile(tracer)


def uninstall_automatic_instrumentation() -> None:
    """Uninstall automatic instrumentation.

    This will stop tracing all function calls.
    """
    current_tracer = sys.getprofile()
    if isinstance(current_tracer, FuncTracer):
        # if the current tracer is a FuncTracer then we are in a nested call to install_automatic_instrumentation
        # so we need to set the previous tracer to the previous tracer of the last tracer
        sys.setprofile(current_tracer.previous_tracer)
    else:
        warnings.warn(
            'uninstall_automatic_instrumentation called without a previous call to install_automatic_instrumentation',
            UserWarning,
        )
