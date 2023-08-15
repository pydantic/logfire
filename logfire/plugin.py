from typing import Any

from pydantic import ValidationError
from pydantic.plugin import OnValidatePython as _OnValidatePython, Plugin
from rich.console import Console

console = Console()


class OnValidatePython(_OnValidatePython):  # type: ignore[misc]
    def enter(
        self,
        input: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        self_instance: Any | None = None,
    ) -> None:
        console.print(self.plugin_settings)
        console.print('input', input)
        console.print('strict', strict)
        console.print('from_attributes', from_attributes)
        console.print('context', context)
        console.print()

    def on_success(self, result: Any) -> None:
        console.print(self.plugin_settings)
        console.print('result', result)
        console.print()

    def on_error(self, error: ValidationError) -> None:
        console.print(self.plugin_settings)
        console.print_json(error.json())
        console.print()


plugin = Plugin(on_validate_python=OnValidatePython)
