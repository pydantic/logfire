from __future__ import annotations as _annotations

import re
from pathlib import Path

from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from logfire import _config_params as config_params

NON_CONFIG_PARAM_ENV_VARS = {
    'LOGFIRE_DISABLE_PYDANTIC_PLUGIN': 'Whether to disable the Pydantic plugin.',
}


def build_environment_variables_table() -> str:
    module_lines = Path(config_params.__file__).read_text().splitlines()
    table: list[str] = []
    table.append('| Name | Description |')
    table.append('| ---- | ----------- |')

    # Include config param env vars.
    for param in config_params.CONFIG_PARAMS.values():
        if not param.env_vars:
            continue
        env_var = param.env_vars[0]
        for idx, line in enumerate(module_lines):
            if f"'{env_var}'" in line:
                break
        description = module_lines[idx + 1]
        if not description.startswith('"""'):
            raise RuntimeError(f'Missing docstring on env var {env_var}.')
        description = description.strip('"')
        table.append(f'| {env_var} | {description} |')

    # Include non-config param env vars.
    for env_var, description in NON_CONFIG_PARAM_ENV_VARS.items():
        table.append(f'| {env_var} | {description} |')

    return '\n'.join(table)


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """
    Called on each file after it is read and before it is converted to HTML.
    """
    if page.file.src_uri != 'configuration.md':
        return markdown
    table_markdown = build_environment_variables_table()
    markdown = re.sub(r'{{ *env_var_table *}}', table_markdown, markdown)
    return markdown
