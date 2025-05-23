from typing import Any

from openinference.instrumentation.langchain import LangChainInstrumentor, _tracer

from logfire._internal.json_encoder import logfire_json_dumps


def instrument_langchain():
    LangChainInstrumentor().instrument()

    def patched_safe_json_dumps(obj: Any, **_: Any) -> str:
        return logfire_json_dumps(obj)

    _tracer.safe_json_dumps = patched_safe_json_dumps  # type: ignore
