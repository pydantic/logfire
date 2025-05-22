import json
from typing import Any

import pydantic
from openinference.instrumentation.langchain import LangChainInstrumentor, _tracer


def instrument_langchain():
    LangChainInstrumentor().instrument()

    def json_default(obj: Any) -> Any:
        try:
            if isinstance(obj, pydantic.BaseModel):
                return obj.model_dump(mode='json', warnings='error', fallback=str)
        except Exception:
            pass
        return str(obj)

    def patched_safe_json_dumps(obj: Any, **kwargs: Any) -> str:
        return json.dumps(obj, default=json_default, ensure_ascii=False, **kwargs)

    _tracer.safe_json_dumps = patched_safe_json_dumps  # type: ignore
