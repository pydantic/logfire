from __future__ import annotations

import os
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic_core import CoreConfig, CoreSchema

import logfire

if TYPE_CHECKING:
    from pydantic import ValidationError
    from pydantic.plugin import (
        ValidateJsonHandlerProtocol,
        ValidatePythonHandlerProtocol,
        ValidateStringsHandlerProtocol,
    )
    from typing_extensions import TypeAlias

    # It might make sense to export the following type alias from `pydantic.plugin`, rather than redefining it here.
    StringInput: TypeAlias = 'dict[str, StringInput]'


class BaseValidateHandler:
    validation_method: ClassVar[str]
    span_stack: ExitStack
    __slots__ = 'schema_name', 'span_stack'

    def __init__(self, schema: CoreSchema, _config: CoreConfig | None, _plugin_settings: dict[str, object]) -> None:
        # We accept the schema, config, and plugin_settings in the init since these are the things
        # that are currently exposed by the plugin to potentially configure the validation handlers.
        self.schema_name = get_schema_name(schema)

    def _on_enter(
        self,
        input_data: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        self_instance: Any | None = None,
    ) -> None:
        self.span_stack = ExitStack()
        self.span_stack.enter_context(
            logfire.span(
                'Pydantic {schema_name} {validation_method}',
                schema_name=self.schema_name,
                validation_method=self.validation_method,
                input_data=input_data,
                span_name=f'pydantic.{self.validation_method}',
            )
        )

    def on_success(self, result: Any) -> None:
        logfire.debug('Validation successful {result=!r}', result=result)
        self.span_stack.close()

    def on_error(self, error: ValidationError) -> None:
        error_count = error.error_count()
        plural = '' if error_count == 1 else 's'
        logfire.warning(
            '{error_count} validation error{plural}',
            error_count=error_count,
            plural=plural,
            errors=error.errors(include_url=False),
        )
        self.span_stack.close()


def get_schema_name(schema: CoreSchema) -> str:
    """
    Find the best name to use for a schema, using the following rules:
    * If the schema represents a model or dataclass, use the name of the class.
    * If the root schema is a wrap/before/after validator, look at its `schema` property.
    * Otherwise use the schema's `type` property.
    """
    schema_type = schema['type']
    if schema_type in {'model', 'dataclass'}:
        return schema['cls'].__name__  # type: ignore
    elif schema_type in {'function-after', 'function-before', 'function-wrap'}:
        return get_schema_name(schema['schema'])  # type: ignore
    else:
        return schema_type


class ValidatePythonHandler(BaseValidateHandler):
    """Implements `pydantic.plugin.ValidatePythonHandlerProtocol`"""

    validation_method = 'validate_python'

    def on_enter(
        self,
        input: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        self_instance: Any | None = None,
    ) -> None:
        self._on_enter(
            input, strict=strict, from_attributes=from_attributes, context=context, self_instance=self_instance
        )


class ValidateJsonHandler(BaseValidateHandler):
    """Implements `pydantic.plugin.ValidateJsonHandlerProtocol`"""

    validation_method = 'validate_json'

    def on_enter(
        self,
        input: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        context: dict[str, Any] | None = None,
        self_instance: Any | None = None,
    ) -> None:
        self._on_enter(input, strict=strict, context=context, self_instance=self_instance)


class ValidateStringsHandler(BaseValidateHandler):
    """Implements `pydantic.plugin.ValidateStringsHandlerProtocol`"""

    validation_method = 'validate_strings'

    def on_enter(
        self, input: StringInput, *, strict: bool | None = None, context: dict[str, Any] | None = None
    ) -> None:
        self._on_enter(input, strict=strict, context=context)


@dataclass
class LogfirePydanticPlugin:
    """Implements `pydantic.plugin.PydanticPluginProtocol`


    Environment Variables:
        LOGFIRE_DISABLE_PYDANTIC_PLUGIN: Set to `1` or `true` to disable the plugin.
            TODO(lig): Use PYDANTIC_DISABLE_PLUGINS instead. See https://github.com/pydantic/pydantic/issues/7709
    """

    enabled: bool = True

    def __init__(self) -> None:
        disable_plugin = os.getenv('LOGFIRE_DISABLE_PYDANTIC_PLUGIN')
        if disable_plugin:
            if disable_plugin.casefold() in ('1', 'true'):
                self.enabled = False
            else:
                warnings.warn(
                    f'"LOGFIRE_DISABLE_PYDANTIC_PLUGIN" env var could be "1" or "true" only, got {disable_plugin}'
                )

    def new_schema_validator(
        self,
        schema: CoreSchema,
        config: CoreConfig | None,
        plugin_settings: dict[str, object],
    ) -> tuple[
        ValidatePythonHandlerProtocol | None, ValidateJsonHandlerProtocol | None, ValidateStringsHandlerProtocol | None
    ]:
        if self.enabled:
            # TODO(Samuel) something more complete and robust
            logfire_settings = plugin_settings.get('logfire')
            if logfire_settings != 'disable' and include_model(schema):
                return (
                    ValidatePythonHandler(schema, config, plugin_settings),
                    ValidateJsonHandler(schema, config, plugin_settings),
                    ValidateStringsHandler(schema, config, plugin_settings),
                )

        return None, None, None


plugin = LogfirePydanticPlugin()

# set of modules to ignore completed
IGNORED_MODULE_PREFIXES: tuple[str, ...] = 'fastapi.', 'logfire_backend.'
# set of tuples of (module, name) of models to ignore
# IGNORED_MODELS: set[tuple[str, str]] = set()


def include_model(schema: CoreSchema) -> bool:
    """
    Check whether a model should be instrumented
    """
    schema_type = schema['type']
    if schema_type in {'model', 'dataclass'}:
        cls: type[Any] = schema['cls']  # type: ignore
        module = cast(str, cls.__module__)  # type: ignore
        if any(module.startswith(prefix) for prefix in IGNORED_MODULE_PREFIXES):
            return False
        # if (module, cls.__name__) in IGNORED_MODELS:
        #     return False
        else:
            # print(module, cls.__name__)
            return True
    elif schema_type in {'function-after', 'function-before', 'function-wrap'}:
        return include_model(schema['schema'])  # type: ignore
    else:
        return True


if TYPE_CHECKING:
    # This is just to ensure we get type checking that the plugin actually implements the expected protocol.
    from pydantic.plugin import PydanticPluginProtocol

    def check_plugin_protocol(_plugin: PydanticPluginProtocol) -> None:
        pass

    check_plugin_protocol(plugin)
