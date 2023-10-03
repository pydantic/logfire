from __future__ import annotations

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


@dataclass
class FuncTracer:
    modules: re.Pattern[str] | None = None
    previous_tracer: ProfileFunction | None = None
    enabled: bool = True
    installed: bool = False

    def __call__(
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
            span_gen = tracer.start_as_current_span(frame.f_code.co_name, end_on_exit=False)
            span = span_gen.__enter__()
            # TODO: this is literally editing the locals of the frame, is there a better way to do this?
            # Users can not only see this but also locals() and such will reflect it!
            frame.f_locals['__span'] = span
        elif event == 'return':
            f = frame
            while f:
                span: Span | None = f.f_locals.get('__span', None)
                if span is not None:
                    span.__exit__(None, None, None)
                    del f.f_locals['__span']
                    break
                f = f.f_back


_TRACER = FuncTracer()


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
        modules_pattern = inspect.stack()[1].filename
    else:
        modules_pattern = '|'.join(f'{Path(inspect.getfile(sys.modules[module])).parent}/.*' for module in modules)
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
