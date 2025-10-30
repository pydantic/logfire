from typing import Any

def check_param_spec_syntax(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return args, kwargs
