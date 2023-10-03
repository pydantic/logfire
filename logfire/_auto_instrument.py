from __future__ import annotations

import importlib
import inspect
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from _typeshed import ProfileFunction

from opentelemetry import trace
from opentelemetry.trace.span import Span

tracer = trace.get_tracer(__name__)


_SPANS: dict[tuple[FrameType, str], Span] = {}


@dataclass
class FuncTracer:
    modules: re.Pattern[str] | None = None
    previous_tracer: ProfileFunction | None = None
    enabled: bool = True
    installed: bool = False

    def __call__(  # noqa: C901
        self,
        frame: FrameType,
        event: str,
        arg: Any,
    ) -> None:
        if self.previous_tracer is not None:
            self.previous_tracer(frame, event, arg)
        if not self.enabled:
            return
        # skip anything not happening in the __main__ module
        # eventually we'd want to add some sort of filtering
        # return if modules match frame.co_code.co_qualname or maodules matches '__main__' and frame.co_code.co_qualname has not prefix
        if self.modules is not None:
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
        if event == 'call':
            name = f'{frame.f_globals["__name__"]}.{getattr(frame.f_code, "co_qualname", frame.f_code.co_name)}'
            attributes = {
                'code.namespace': frame.f_globals['__name__'],
                'code.function': frame.f_code.co_name,
            }
            if frame.f_back is not None:
                attributes.update(
                    {
                        'code.filepath': frame.f_back.f_code.co_filename,
                        'code.lineno': frame.f_back.f_lineno,
                    }
                )
            span_gen = tracer.start_as_current_span(name, end_on_exit=False, attributes=attributes)
            span = span_gen.__enter__()
            _SPANS[(frame, 'call')] = span
        elif event == 'c_call':
            name = f'{arg.__module__}.{arg.__name__}'
            attributes = {
                'code.namespace': arg.__module__,
                'code.function': arg.__name__,
                'code.lineno': frame.f_lineno,
                'code.filepath': frame.f_code.co_filename,
            }
            span_gen = tracer.start_as_current_span(name, end_on_exit=False, attributes=attributes)
            span = span_gen.__enter__()
            _SPANS[(frame, 'c_call')] = span
        elif event == 'return':
            f = frame
            while f:
                span: Span | None = _SPANS.pop((f, 'call'), None)
                if span is not None:
                    span.__exit__(None, None, None)
                    break
                f = f.f_back
        elif event == 'c_return':
            f = frame
            while f:
                span: Span | None = _SPANS.pop((f, 'c_call'), None)
                if span is not None:
                    span.__exit__(None, None, None)
                    break
                f = f.f_back


_TRACER = FuncTracer()


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


def install_automatic_instrumentation(modules: list[str] | None = None) -> None:
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
    _TRACER.modules = re.compile(modules_pattern)
    _TRACER.enabled = True
    if not _TRACER.installed:
        _TRACER.previous_tracer = sys.getprofile()
        sys.setprofile(_TRACER)
        _TRACER.installed = True


def uninstall_automatic_instrumentation() -> None:
    """Uninstall automatic instrumentation.

    This will stop tracing all function calls.
    """
    _TRACER.enabled = False
