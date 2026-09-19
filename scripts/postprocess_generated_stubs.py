"""Apply the small corrections that mypy's stubgen cannot represent itself."""

from __future__ import annotations

from pathlib import Path


def postprocess_init_pyi(content: str) -> str:
    """Resolve module-level ``Incomplete`` declarations through the default instance."""
    incomplete = ': Incomplete'
    lines = content.splitlines()
    try:
        span_index = lines.index('span: Incomplete')
    except ValueError:
        return content

    new_end_lines = ['DEFAULT_LOGFIRE_INSTANCE = Logfire()']
    for line in lines[span_index:]:
        if line.endswith(incomplete):
            prefix = line[: -len(incomplete)]
            new_end_lines.append(f'{prefix} = DEFAULT_LOGFIRE_INSTANCE.{prefix}')
        else:
            new_end_lines.append(line)
    lines.remove('from _typeshed import Incomplete')
    lines[span_index - 1 :] = new_end_lines
    return '\n'.join(lines) + '\n'


def postprocess_feature_flags_pyi(content: str) -> str:
    """Preserve the generic constructor inference that stubgen strips from annotated self."""
    precise_alias = 'InferableFlagValue = bool | str | int | float | Enum | BaseModel\n'
    generated_alias = 'InferableFlagValue = Any\n'
    generated_constructor = 'def __init__(self, name: str, *, default: InferableFlagT,'
    typed_constructor = 'def __init__(self: Flag[InferableFlagT], name: str, *, default: InferableFlagT,'
    content = content.replace(
        'FlagEvaluationReason: Incomplete',
        "FlagEvaluationReason = Literal['cached', 'default', 'disabled', 'error', 'split', 'stale', 'static', 'targeting_match', 'unknown']",
    ).replace(
        'FlagErrorCode: Incomplete',
        "FlagErrorCode = Literal['flag_not_found', 'general', 'invalid_context', 'parse_error', 'provider_fatal', 'provider_not_ready', 'targeting_key_missing', 'type_mismatch']",
    )
    if ': Incomplete' not in content:
        content = content.replace('from _typeshed import Incomplete\n', '')
    if (
        'from typing import ' in content
        and 'Literal' not in content.split('from typing import ', 1)[1].split('\n', 1)[0]
    ):
        content = content.replace('from typing import ', 'from typing import Literal, ', 1)

    if precise_alias not in content:
        raise ValueError('The generated InferableFlagValue alias changed; update the stub post-processing contract.')
    generated_alias_count = content.count(generated_alias)
    if generated_alias_count == 1:
        content = content.replace(generated_alias, '', 1)
    elif generated_alias_count != 0:
        raise ValueError('The generated InferableFlagValue alias was emitted more than once.')

    generated_constructor_count = content.count(generated_constructor)
    typed_constructor_count = content.count(typed_constructor)
    if generated_constructor_count == 1 and typed_constructor_count == 0:
        return content.replace(generated_constructor, typed_constructor, 1)
    if generated_constructor_count == 0 and typed_constructor_count == 1:
        return content
    raise ValueError('The generated Flag constructor signature changed; update the stub post-processing contract.')


def postprocess_variables_abstract_pyi(content: str) -> str:
    """Preserve the provider lifecycle state alias that stubgen cannot infer from Literal."""
    content = content.replace(
        'VariableProviderEvaluationState: Incomplete',
        "VariableProviderEvaluationState = Literal['not_ready', 'ready', 'stale', 'error', 'fatal']",
    )
    if (
        'from typing import ' in content
        and 'Literal' not in content.split('from typing import ', 1)[1].split('\n', 1)[0]
    ):
        content = content.replace('from typing import ', 'from typing import Literal, ', 1)
    return content


def postprocess_generated_stubs(api_dir: Path) -> list[Path]:
    """Rewrite generated stub files and return the paths that changed."""
    processors = {
        api_dir / '__init__.pyi': postprocess_init_pyi,
        api_dir / 'experimental' / 'feature_flags.pyi': postprocess_feature_flags_pyi,
        api_dir / 'variables' / 'abstract.pyi': postprocess_variables_abstract_pyi,
    }
    changed: list[Path] = []
    for path, processor in processors.items():
        original = path.read_text()
        processed = processor(original)
        if processed != original:
            path.write_text(processed)
            changed.append(path)
    return changed


if __name__ == '__main__':
    postprocess_generated_stubs(Path(__file__).parent.parent / 'logfire-api' / 'logfire_api')
