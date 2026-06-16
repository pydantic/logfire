import logfire
from _typeshed import Incomplete
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from logfire._internal.config import TemplateMismatchPolicy
from logfire.variables.abstract import ResolvedVariable
from logfire.variables.composition import ComposedReference
from logfire.variables.config import VariableConfig
from typing import Any, Generic, Protocol, TypeVar
from typing_extensions import TypeIs

__all__ = ['ResolveFunction', 'is_resolve_function', 'Variable', 'TemplateVariable', 'TemplateInputsMismatchError', 'targeting_context']

class TemplateInputsMismatchError(Exception):
    """Render-time `{{field}}` mismatch raised under the strict policy.

    Raised by `TemplateVariable.get(inputs)` when the resolved template
    references a `{{field}}` not declared in the variable's `inputs_type`
    and the active `template_mismatch_policy` is `'error'`.

    Distinct from `HandlebarsError` so it bypasses the SDK's composition-
    failure fallback and propagates to the caller — the `'error'` policy
    is meant to fail loudly, not silently degrade to the code default.
    """
T_co = TypeVar('T_co', covariant=True)
InputsT = TypeVar('InputsT')

@dataclass
class _TargetingContextData:
    """Internal data structure for targeting context."""
    default: str | None = ...
    by_variable: dict[str, str] = field(default_factory=dict[str, str])

class ResolveFunction(Protocol[T_co]):
    """Protocol for functions that resolve variable values based on context."""
    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        """Resolve the variable value given a targeting key and attributes."""

class _RenderFunction(Protocol):
    def __call__(self, serialized_json: str, /) -> str:
        """Render a serialized JSON value before deserialization."""

def is_resolve_function(f: Any) -> TypeIs[ResolveFunction[Any]]:
    """Check if a callable matches the ResolveFunction signature.

    A resolve function is any callable that can be called with exactly two positional arguments
    (targeting_key and attributes). This includes:
    - Functions/lambdas with exactly 2 parameters
    - Functions with 2+ parameters where all after the first 2 have defaults
    - Functions with *args or **kwargs

    Args:
        f: The object to check.

    Returns:
        True if the callable can be invoked with two positional arguments.
    """

@dataclass
class _ResolveAttempt:
    """Outcome of a single compose -> render -> deserialize attempt.

    `ok=True` carries the successful `result`. `ok=False` carries the
    `exception` and the pipeline `stage` that failed, which the caller uses to
    decide how to fall back (e.g. a `'composition'` failure on the code default
    triggers a non-strict retry).
    """
    ok: bool
    result: ResolvedVariable[Any] | None = ...
    exception: Exception | None = ...
    stage: _FailureStage = ...
    composed: list[ComposedReference] = field(default_factory=list['ComposedReference'])

class Variable(Generic[T_co]):
    """A managed variable that can be resolved dynamically based on configuration."""
    name: str
    value_type: type[T_co]
    default: T_co | ResolveFunction[T_co]
    description: str | None
    logfire_instance: logfire.Logfire
    type_adapter: Incomplete
    def __init__(self, name: str, *, type: type[T_co], default: T_co | ResolveFunction[T_co], description: str | None = None, logfire_instance: logfire.Logfire) -> None:
        """Create a new managed variable.

        Args:
            name: Unique name identifying this variable.
            type: The expected type of this variable's values, used for validation.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            description: Optional human-readable description of what this variable controls.
            logfire_instance: The Logfire instance this variable is associated with. Used to determine config, etc.
        """
    @contextmanager
    def override(self, value: T_co | ResolveFunction[T_co]) -> Generator[None]:
        '''Context manager to temporarily override this variable\'s value.

        Inside the `with` block, every `get()` call on this variable returns
        *value* (or the result of calling it as a `ResolveFunction`) instead
        of consulting the provider or code default.

        ## Composition still applies

        Overrides **do** participate in `@{ref}@` composition: *value* runs
        through the same compose → render → deserialize pipeline as a stored
        value, so it can stand in for a candidate stored value (e.g. during
        iterative optimization) and resolve identically to how it would once
        pushed. If you override with the string `\'hi @{user}@\'`, the
        `@{user}@` *is* expanded against the live provider/config.

        ## Template rendering still applies to TemplateVariable

        For `TemplateVariable.get(inputs)`, `{{...}}` rendering against
        *inputs* runs on the override the same way it would on a
        provider value — *as long as the override is JSON-serializable*.
        For example, overriding with `\'Hi {{name}}\'` and calling
        `get(Inputs(name=\'Alice\'))` yields `\'Hi Alice\'`.

        ## Unserializable overrides come back verbatim

        If *value* can\'t be serialized through the variable\'s type adapter
        (e.g. an arbitrary Python object on a `Variable[object]`), the
        override is returned exactly as you passed it in, with no
        serialize/deserialize round-trip and no template render pass. This
        matches the "literal user choice" intent — a non-JSON Python value
        is by definition not a template, so there\'s nothing to render.

        Args:
            value: The value to use within this context, or a function that computes
                the value based on targeting_key and attributes.
        '''
    async def refresh(self, force: bool = False):
        """Asynchronously refresh the variable."""
    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
    def to_config(self) -> VariableConfig:
        """Create a VariableConfig from this Variable instance.

        This creates a minimal config with just the name, schema, and example.
        No labels or versions are created - use this to generate a template config that can be edited.

        Returns:
            A VariableConfig with minimal configuration.
        """
    def get(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None, *, label: str | None = None) -> ResolvedVariable[T_co]:
        """Resolve the variable and return full details including label, version, and any errors.

        Args:
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
                If not provided, falls back to contextvar targeting key (set via targeting_context),
                then to the current trace ID if there is an active trace.
            attributes: Optional attributes for condition-based targeting rules.
            label: Optional explicit label name to select. If provided, bypasses rollout
                weights and targeting, directly selecting the specified label. If the label
                doesn't exist in the configuration, falls back to default resolution.

        Returns:
            A ResolvedVariable object containing the resolved value, selected label,
            version, and any errors that occurred.
        """

class TemplateVariable(Variable[T_co], Generic[T_co, InputsT]):
    """A managed variable with integrated template rendering.

    Like `Variable`, but `get()` requires `inputs` and automatically renders
    Handlebars `{{placeholder}}` templates in the resolved value before returning.
    The pipeline is: resolve → compose `@{refs}@` → render `{{}}` → deserialize.
    """
    inputs_type: type[InputsT]
    template_mismatch_policy: TemplateMismatchPolicy | None
    def __init__(self, name: str, *, type: type[T_co], default: T_co | ResolveFunction[T_co], inputs_type: type[InputsT], description: str | None = None, logfire_instance: logfire.Logfire, template_mismatch_policy: TemplateMismatchPolicy | None = None) -> None:
        """Create a new template variable.

        Args:
            name: Unique name identifying this variable.
            type: The expected type of this variable's values, used for validation.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            inputs_type: The type (typically a Pydantic `BaseModel`) describing the expected
                template inputs. Used for type-safe `get(inputs)` calls and JSON schema generation.
            description: Optional human-readable description of what this variable controls.
            logfire_instance: The Logfire instance this variable is associated with.
            template_mismatch_policy: Per-variable override of the render-time
                `{{field}}` mismatch policy. `None` (default) inherits from
                `VariablesOptions` / `LocalVariablesOptions`.
        """
    def get_template_inputs_schema(self) -> dict[str, Any]:
        """Return the JSON schema derived from `inputs_type`."""
    def to_config(self) -> VariableConfig:
        """Create a VariableConfig, including `template_inputs_schema`."""
    def get(self, inputs: InputsT, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None, *, label: str | None = None) -> ResolvedVariable[T_co]:
        """Resolve the variable, render templates with the given inputs, and return the result.

        The resolution pipeline is:
        1. Fetch serialized value from provider (or use default)
        2. Expand `@{variable_name}@` composition references
        3. Render `{{placeholder}}` Handlebars templates using `inputs`
        4. Deserialize to the variable's type

        Args:
            inputs: Template context values. Typically a Pydantic `BaseModel` instance
                matching `inputs_type`. All `{{placeholder}}` expressions in the value
                are rendered using this context.
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.
            label: Optional explicit label name to select.

        Returns:
            A ResolvedVariable with the fully rendered and deserialized value.

        Raises:
            TemplateInputsMismatchError: When `template_mismatch_policy` resolves
                to `'error'` and the post-composition template references a
                `{{field}}` not declared in `inputs_type`.
        """

@contextmanager
def targeting_context(targeting_key: str, variables: Sequence[Variable[Any] | TemplateVariable[Any, Any]] | None = None) -> Generator[None]:
    '''Set the targeting key for variable resolution within this context.

    The targeting key is used for deterministic label selection - the same targeting key
    will always resolve to the same label for a given variable configuration.

    Args:
        targeting_key: The targeting key to use for deterministic label selection
            (e.g., user ID, organization ID).
        variables: If provided, only apply this targeting key to these specific variables.
            If not provided, this becomes the default targeting key for all variables.

    Variable-specific targeting always takes precedence over the default, regardless
    of nesting order. Call-site explicit targeting_key still wins over everything.

    Example:
        # Set default targeting for all variables
        with targeting_context("user123"):
            value = my_variable.get()  # uses "user123"

        # Set targeting for specific variables
        with targeting_context("org456", variables=[org_variable]):
            org_value = org_variable.get()  # uses "org456"
            other_value = other_variable.get()  # uses default or trace_id

        # Combine default and specific - order doesn\'t matter for precedence
        with targeting_context("user123"):
            with targeting_context("org456", variables=[org_variable]):
                org_value = org_variable.get()  # uses "org456" (specific wins)
                other_value = other_variable.get()  # uses "user123" (default)
    '''
