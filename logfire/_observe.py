import dataclasses
import json  # TODO(lig): use more performant json library
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property, wraps
from inspect import Parameter as SignatureParameter, signature as inspect_signature
from pathlib import Path
from types import FrameType, TracebackType
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypedDict, TypeVar, cast

import httpx
import rich.traceback
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, Tracer, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import format_span_id
from opentelemetry.util.types import AttributeValue
from pydantic import Field
from pydantic_core import ValidationError, to_json
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import LiteralString

from logfire._json_encoder import LogfireEncoder
from logfire.credentials import LogfireCredentials, get_credentials, get_credentials_file
from logfire.formatter import logfire_format
from logfire.version import VERSION

LEVEL_KEY = 'logfire.level'
MSG_TEMPLATE_KEY = 'logfire.msg_template'
LOG_TYPE_KEY = 'logfire.log_type'
TAGS_KEY = 'logfire.tags'
NULL_ARGS_KEY = 'logfire.null_args'
START_PARENT_ID = 'logfire.start_parent_id'
LINENO = 'logfire.lineno'
FILENAME = 'logfire.filename'
NON_SCALAR_VAR_SUFFIX = '__JSON'
LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']
LogTypeType = Literal['log', 'start_span', 'real_span']

_RETURN = TypeVar('_RETURN')
_PARAMS = ParamSpec('_PARAMS')
_POSITIONAL_PARAMS = {SignatureParameter.POSITIONAL_ONLY, SignatureParameter.POSITIONAL_OR_KEYWORD}

_cwd = Path('.').resolve()


class LogfireConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='LOGFIRE_')

    api_root: str = 'http://localhost:4318'
    project_id: str | None = None
    token: str | None = None
    credentials_file: Path = Field(default_factory=get_credentials_file)
    """
    `credentials_file` is what will be used to load the `project_id` and `token` if they are not otherwise specified.
    It is also the file that will be used to store those values on disk when they are retrieved from the server
    when creating a new project.
    """

    service_name: str = 'logfire'
    verbose: bool = False

    # TODO(DavidM): Implement the new API for configuring:
    #   https://linear.app/pydantic/issue/PYD-246/logfire-sdk-setup.

    @property
    def projects_endpoint(self) -> str:
        return f'{self.api_root}/v1/projects/'

    def request_new_project_credentials(self, project_id: str | None) -> LogfireCredentials:
        # use the explicitly-specified project ID if present
        params = {'project_id': project_id} if project_id else None
        response = httpx.post(self.projects_endpoint, params=params)
        response.raise_for_status()
        return LogfireCredentials.model_validate_json(response.content)

    def get_credentials(self) -> LogfireCredentials:
        return get_credentials(self.project_id, self.token, self.credentials_file, self.request_new_project_credentials)

    def get_client(self) -> 'LogfireClient':
        creds = self.get_credentials()

        return LogfireClient(
            api_root=self.api_root,
            service_name=self.service_name,
            project_id=creds.project_id,
            token=creds.token,
            verbose=self.verbose,
        )


@dataclasses.dataclass
class LogfireClient:
    api_root: str
    service_name: str
    project_id: str
    token: str
    verbose: bool

    provider: TracerProvider = dataclasses.field(init=False)
    processor: BatchSpanProcessor = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.provider = TracerProvider(resource=Resource(attributes={'service.name': self.service_name}))
        self.set_exporter()
        self.print_dashboard_url()

    @property
    def traces_endpoint(self) -> str:
        return f'{self.api_root}/v1/traces/{self.project_id}'

    @property
    def dashboard_url_endpoint(self) -> str:
        return f'{self.api_root}/dash/{self.project_id}'

    @property
    def headers(self) -> dict[str, str]:
        return {'Authorization': self.token, 'User-Agent': f'logfire/{VERSION}'}

    def set_exporter(self, exporter: SpanExporter | None = None) -> None:
        self.provider = TracerProvider(resource=Resource(attributes={'service.name': self.service_name}))
        self.self_log(f'Configured tracer provider with service.name={self.service_name!r}')

        exporter = exporter or self._get_default_exporter()
        # TODO(DavidH): may want to make some of the processor options configurable so
        #   that overhead vs latency tradeoff can be adjusted, for now set for
        #   minimum latency which will be nicest on small workloads
        self.processor = BatchSpanProcessor(exporter, schedule_delay_millis=1)

        # FIXME big hack - without this `set_exporter` actually just adds another exporter!
        self.provider._active_span_processor._span_processors = ()  # type: ignore

        self.provider.add_span_processor(self.processor)
        self.self_log(f'Configured span exporter with endpoint={self.traces_endpoint!r}')

    def print_dashboard_url(self) -> None:
        response = httpx.get(self.dashboard_url_endpoint, headers=self.headers)
        try:
            response.raise_for_status()
        except Exception:
            print(response.text)  # TODO(lig): a proper log maybe?
            raise
        dashboard_url = response.json()['dashboardUrl']
        print(f'*** View logs at {dashboard_url} ***')

    def self_log(self, __msg: str) -> None:
        # TODO: probably want to make this more configurable/etc.
        if self.verbose:
            print(__msg)

    def _get_default_exporter(self) -> OTLPSpanExporter:
        return OTLPSpanExporter(endpoint=self.traces_endpoint, headers=self.headers)


class LogFireSpan(TypedDict):
    real_span: Span
    start_span: Span


@contextmanager
def record_exception(span: Span) -> Iterator[None]:
    """Context manager for recording an exception on a span.

    This will record the exception on the span and re-raise it.

    Args:
        span: The span to record the exception on.

    Raises:
        Any: The exception that was raised.
    """
    try:
        yield
    # NOTE: We don't want to catch `BaseException` here, since that would catch
    # things like `KeyboardInterrupt` and `SystemExit`. Also, `Exception` is the one caught
    # by the `tracer.use_span` context manager internally.
    except Exception:
        exc_type, exc_value, traceback = cast(tuple[type[Exception], Exception, TracebackType], sys.exc_info())
        # NOTE(Marcelo): You can pass `show_locals=True` to `rich.traceback.Traceback.from_exception`
        # to get the local variables in the traceback. For now, we're not doing that.
        tb = rich.traceback.Traceback.from_exception(exc_type=exc_type, exc_value=exc_value, traceback=traceback)

        attributes: dict[str, bytes] = {'exception.logfire.trace': to_json(tb.trace), 'exception.logfire.data': b''}
        if exc_type == ValidationError:
            exc = cast(ValidationError, exc_value)
            data = json.dumps({'errors': exc.errors(include_url=False)}, cls=LogfireEncoder, separators=(',', ':'))
            attributes['exception.logfire.data'] = data.encode()

        span.record_exception(exc_value, attributes=attributes, escaped=True)
        raise


class Observe:
    def __init__(self, config: LogfireConfig | None = None):
        self._tracer: ContextVar[Tracer | None] = ContextVar('_tracer', default=None)
        self._config: LogfireConfig = config or LogfireConfig()
        self._tags: tuple[str, ...] = ()

    @cached_property
    def _client(self) -> LogfireClient:
        return self._config.get_client()

    # Configuration
    def configure(self, config: LogfireConfig | None = None, exporter: SpanExporter | None = None) -> None:
        if config is not None:
            self._config = config

        self.__dict__.pop('_client', None)  # Clear the cached property if it has been generated
        self._client.set_exporter(exporter)

    # Tags
    def tags(self, first_tag: str, /, *more_tags: str) -> 'TaggedObserve':
        return TaggedObserve((first_tag,) + more_tags, self)

    def _set_tags(self, tags: tuple[str, ...]) -> None:
        self._tags = tags

    def _pop_tags(self) -> tuple[str, ...] | None:
        if not self._tags:
            return None
        tags = self._tags
        self._tags = ()
        return tags

    # Spans
    @contextmanager
    def span(self, span_name: str, msg_template: LiteralString, /, **kwargs: Any) -> Iterator[LogFireSpan]:
        """Context manager for creating a span."""
        tracer = self._get_context_tracer()
        start_time = int(time.time() * 1e9)

        start_parent_id = self._start_parent_id()
        logfire_attributes = self._logfire_attributes('real_span', start_parent_id=start_parent_id)
        with tracer.start_as_current_span(
            span_name, attributes=logfire_attributes, start_time=start_time, record_exception=False
        ) as real_span:
            real_span = cast(Span, real_span)
            start_span = self._span_start(
                tracer=tracer,
                outer_parent_id=start_parent_id,
                start_time=start_time,
                msg_template=msg_template,
                kwargs=kwargs,
            )

            with record_exception(real_span):
                yield {'real_span': real_span, 'start_span': start_span}

    def instrument(
        self,
        msg_template: LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool | None = None,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        """Decorator for instrumenting a function as a span."""
        tracer = self._get_context_tracer()

        if extract_args is None:
            extract_args = bool(msg_template and '{' in msg_template)

        def decorator(func: Callable[_PARAMS, _RETURN]) -> Callable[_PARAMS, _RETURN]:
            nonlocal span_name
            if span_name is None:
                span_name_ = f'{func.__module__}.{func.__name__}'
            else:
                span_name_ = span_name
            self._self_log(f'Instrumenting {func=} {span_name=}')

            if extract_args:
                sig = inspect_signature(func)
                pos_params = tuple(n for n, p in sig.parameters.items() if p.kind in _POSITIONAL_PARAMS)

            @wraps(func)
            def wrapper(*args: _PARAMS.args, **kwargs: _PARAMS.kwargs) -> _RETURN:
                start_time = int(time.time() * 1e9)

                if extract_args:
                    pos_args = {k: v for k, v in zip(pos_params, args)}
                    extracted_kwargs = {**pos_args, **kwargs}
                else:
                    extracted_kwargs = {}

                start_parent_id = self._start_parent_id()
                attributes = self._logfire_attributes('real_span')
                with tracer.start_as_current_span(
                    span_name_, attributes=attributes, start_time=start_time, record_exception=False
                ) as real_span:
                    self._span_start(
                        tracer=tracer,
                        outer_parent_id=start_parent_id,
                        start_time=start_time,
                        msg_template=msg_template or span_name_,
                        kwargs=extracted_kwargs,
                    )
                    with record_exception(cast(Span, real_span)):
                        return func(*args, **kwargs)

            return wrapper

        return decorator

    # Logging
    def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any, _frame_depth: int = 1) -> None:
        msg = logfire_format(msg_template, kwargs)
        tracer = self._get_context_tracer()
        start_time = int(time.time() * 1e9)  # OpenTelemetry uses ns for timestamps

        call_frame: FrameType = sys._getframe(_frame_depth)  # type: ignore
        lineno = call_frame.f_lineno
        file = Path(call_frame.f_code.co_filename)
        if file.is_absolute():
            try:
                file = file.relative_to(_cwd)
            except ValueError:
                # happens if filename path is not within CWD
                pass

        user_attributes = Observe.user_attributes(kwargs)
        logfire_attributes = self._logfire_attributes(
            'log', msg_template=msg_template, level=level, lineno=lineno, filename=str(file)
        )
        attributes = {**user_attributes, **logfire_attributes}

        span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes)
        span.end(start_time)
        with trace.use_span(span):
            pass

    def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'debug', kwargs, _frame_depth=2)

    def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'info', kwargs, _frame_depth=2)

    def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'notice', kwargs, _frame_depth=2)

    def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'warning', kwargs, _frame_depth=2)

    def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'error', kwargs, _frame_depth=2)

    def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'critical', kwargs, _frame_depth=2)

    # Utilities
    @contextmanager
    def context_tracer(self, name: str) -> Iterator[None]:
        tracer = self._get_tracer(name)
        token = self._tracer.set(tracer)
        try:
            yield
        finally:
            self._tracer.reset(token)

    @staticmethod
    def _start_parent_id() -> str | None:
        span_id = trace.get_current_span(None).get_span_context().span_id
        if span_id == 0:
            return None
        return format_span_id(span_id)

    def _span_start(
        self,
        *,
        tracer: Tracer,
        outer_parent_id: str | None,
        start_time: int,
        msg_template: str,
        kwargs: dict[str, Any],
    ) -> Span:
        """Send a zero length span at the start of the main span to represent the span opening.

        This is required since the span itself isn't sent until it's closed.
        """
        msg = logfire_format(msg_template, kwargs)

        logfire_attributes = self._logfire_attributes(
            'start_span', msg_template=msg_template, start_parent_id=outer_parent_id
        )
        user_attributes = Observe.user_attributes(kwargs)
        attributes = {**logfire_attributes, **user_attributes}

        start_span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes)
        start_span.end(start_time)
        with trace.use_span(start_span):
            pass

        return start_span  # type: ignore

    def _get_context_tracer(self) -> Tracer:
        tracer = self._tracer.get()
        if tracer is None:
            return self._get_tracer(self._config.service_name)
        return tracer

    def _get_tracer(self, name: str) -> Tracer:
        # NOTE(DavidM): Should we add version, schema_url?
        return trace.get_tracer(name, tracer_provider=self._client.provider)  # type: ignore

    def _logfire_attributes(
        self,
        log_type: LogTypeType,
        *,
        msg_template: str | None = None,
        level: LevelName | None = None,
        start_parent_id: str | None = None,
        lineno: int | None = None,
        filename: str | None = None,
    ) -> dict[str, AttributeValue]:
        tags = self._pop_tags()
        return _dict_not_none(
            **{
                LOG_TYPE_KEY: log_type,
                LEVEL_KEY: level,
                MSG_TEMPLATE_KEY: msg_template,
                TAGS_KEY: tags,
                START_PARENT_ID: start_parent_id,
                LINENO: lineno,
                FILENAME: filename,
            }
        )

    @staticmethod
    def user_attributes(attributes: dict[str, Any]) -> dict[str, AttributeValue]:
        """Prepare attributes for sending to OpenTelemetry.

        This will convert any non-OpenTelemetry compatible types to JSON.
        """
        prepared: dict[str, AttributeValue] = {}
        null_args: list[str] = []

        for key, value in attributes.items():
            match value:
                case None:
                    null_args.append(key)
                case str() | bool() | int() | float():
                    prepared[key] = value
                case _:
                    # TODO(Marcelo): Should we add the `separators=(",", ":")`?
                    # TODO(lig): A separator seems like a good idea
                    # Next person that reads this decides, and removes this comment.
                    prepared[key + NON_SCALAR_VAR_SUFFIX] = json.dumps(value, cls=LogfireEncoder)

        if null_args:
            prepared[NULL_ARGS_KEY] = tuple(null_args)

        return prepared

    def _self_log(self, __msg: str) -> None:
        self._client.self_log(__msg)


class TaggedObserve:
    """Proxy class to to make the observer.tags() syntax possible."""

    def __init__(self, tags: tuple[str, ...], observe: Observe):
        self._tags = tags
        self._observe = observe

    if TYPE_CHECKING:

        @contextmanager
        def span(self, span_name: str, msg_template: LiteralString, /, **kwargs: Any) -> Iterator[LogFireSpan]:
            ...

        def instrument(
            self,
            tracer_name: str | None = None,
            span_name: str | None = None,
            msg_template: LiteralString | None = None,
            inspect: bool = False,
        ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
            ...

        def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
            ...

        def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

    else:

        def __getattr__(self, item):
            self._observe._set_tags(self._tags)
            return getattr(self._observe, item)

    def tags(self, first_tag: str, *args: str) -> 'TaggedObserve':
        return TaggedObserve(self._tags + (first_tag,) + tuple(args), self._observe)


def _dict_not_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}
