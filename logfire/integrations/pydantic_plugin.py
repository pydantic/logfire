from __future__ import annotations

import os
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console

import logfire

if TYPE_CHECKING:
    from pydantic import ValidationError

console = Console()


class ValidatePythonHandler:
    """Implements `pydantic.plugin.ValidatePythonHandlerProtocol`"""

    span_stack: ExitStack

    def on_enter(
        self,
        input: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        self_instance: Any | None = None,
    ) -> None:
        self.span_stack = ExitStack()
        self.span_stack.enter_context(
            logfire.span(span_name='logfire.pydantic.validate_python', msg_template='{input=}', input=input)
        )

    def on_success(self, result: Any) -> None:
        logfire.debug('{result=}', result=result)
        self.span_stack.close()

    def on_error(self, error: ValidationError) -> None:
        logfire.error('{error=}', error=error)
        self.span_stack.close()


@dataclass
class Plugin:
    """Implements `pydantic.plugin.PydanticPluginProtocol`


    Environment Variables:
        LOGFIRE_DISABLE_PYDANTIC_PLUGIN: Set to `1` or `true` to disable the plugin.
            TODO(lig): Use PYDANTIC_DISABLE_PLUGINS instead. See https://github.com/pydantic/pydantic/issues/7709
    """

    _disabled: bool = False

    def __init__(self) -> None:
        disable_plugin = os.getenv('LOGFIRE_DISABLE_PYDANTIC_PLUGIN')
        if disable_plugin:
            if disable_plugin.casefold() in ('1', 'true'):
                self._disabled = True
            else:
                warnings.warn(
                    f'"LOGFIRE_DISABLE_PYDANTIC_PLUGIN" env var could be "1" or "true" only, got {disable_plugin}'
                )

    def new_schema_validator(
        self, _schema: dict[str, object], _config: dict[str, object] | None, _plugin_settings: dict[str, object]
    ) -> tuple[ValidatePythonHandler | None, None, None]:
        if self._disabled:
            return None, None, None
        return ValidatePythonHandler(), None, None


plugin = Plugin()
