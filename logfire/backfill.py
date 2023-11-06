from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Union

from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from typing_extensions import Annotated, Self

from . import LevelName

try:
    from pydantic import BaseModel, ConfigDict, Field, validate_call
except ImportError as e:
    raise ImportError('pydantic is required to use logfire.import, run `pip install logfire[backfill]`') from e


__all__ = 'generate_trace_id', 'generate_span_id', 'RecordLog', 'StartSpan', 'EndSpan', 'PrepareBackfill'
ID_GENERATOR = RandomIdGenerator()


def generate_trace_id() -> int:
    return ID_GENERATOR.generate_trace_id()


def generate_span_id() -> int:
    return ID_GENERATOR.generate_span_id()


pydantic_config = ConfigDict(plugin_settings={'logfire': 'disable'})


class RecordLog(BaseModel):
    model_config = pydantic_config
    type: Literal['log'] = 'log'
    msg_template: str
    level: LevelName
    service_name: str
    attributes: Dict[str, Any]
    trace_id: int = Field(default_factory=generate_trace_id)
    parent_span_id: Union[int, None] = None
    timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None


class StartSpan(BaseModel):
    model_config = pydantic_config
    type: Literal['start_span'] = 'start_span'
    span_name: str
    msg_template: str
    service_name: str
    log_attributes: Dict[str, Any]
    span_id: int = Field(default_factory=generate_span_id)
    trace_id: int = Field(default_factory=generate_trace_id)
    parent_span_id: Union[int, None] = None
    start_timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None


class EndSpan(BaseModel):
    model_config = pydantic_config
    type: Literal['end_span'] = 'end_span'
    span_id: int
    end_timestamp: Union[datetime, None] = None


class PrepareBackfill:
    def __init__(self, store_path: Union[Path, str]):
        self.store_path = Path(store_path)
        self.write_file = None
        self.open_spans: set[int] = set()

    def __enter__(self) -> Self:
        self.write_file = self.store_path.open('wb')
        return self

    @validate_call(config=pydantic_config)
    def write(
        self, data: Annotated[Union[RecordLog, StartSpan, EndSpan], Field(discriminator='type')]
    ) -> Union[RecordLog, StartSpan, EndSpan]:
        assert self.write_file is not None, 'PrepareBackfill must be used as a context manager'
        if data.type == 'start_span':
            assert data.span_id not in self.open_spans, f'start span ID {data.span_id} found in open spans'
            self.open_spans.add(data.span_id)
        if data.type == 'end_span':
            assert data.span_id in self.open_spans, f'end span ID {data.span_id} not found in open spans'
            self.open_spans.remove(data.span_id)

        self.write_file.write(data.__pydantic_serializer__.to_json(data) + b'\n')
        return data

    def __exit__(self, *_: Any) -> None:
        if self.write_file is not None:
            self.write_file.close()
