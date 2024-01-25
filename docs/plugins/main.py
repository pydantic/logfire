from __future__ import annotations as _annotations

import re
import subprocess
from pathlib import Path

import tomllib
from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from logfire import _config_params as config_params


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """
    Called on each file after it is read and before it is converted to HTML.
    """
    markdown = build_environment_variables_table(markdown, page)
    markdown = logfire_print_help(markdown, page)
    markdown = install_logfire(markdown, page)
    markdown = install_extras_table(markdown, page)
    return markdown


def logfire_print_help(markdown: str, page: Page) -> str:
    if page.file.src_uri != 'index.md':
        return markdown

    output = subprocess.run(['logfire', '--help'], capture_output=True, check=True)
    logfire_help = output.stdout.decode()
    return re.sub(r'{{ *logfire_help *}}', logfire_help, markdown)


def build_environment_variables_table(markdown: str, page: Page) -> str:
    """Build the environment variables table for the configuration page.

    Check http://127.0.0.1:8000/configuration/#using-environment-variables.
    """
    if page.file.src_uri != 'configuration.md':
        return markdown

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

    table_markdown = '\n'.join(table)
    return re.sub(r'{{ *env_var_table *}}', table_markdown, markdown)


def install_logfire(markdown: str, page: Page) -> str:
    """Build the installation instructions for each integration."""
    if not page.file.src_uri.startswith('integrations/'):
        return markdown

    # Match instructions like "{{ install_logfire(extras=['fastapi']) }}". Get the extras, if any.
    match = re.search(r'{{ *install_logfire\((.*)\) *}}', markdown)
    extras = match.group(1).split('=')[1].strip('[]').strip('\'"').split(',') if match else []

    # Build the installation instructions.
    package = 'logfire' if not extras else f"'logfire[{','.join(extras)}]'"
    instructions = f"""
=== "PIP"
    ```bash
    pip install {package} --extra-index-url \\
        https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

=== "Poetry"
    ```bash
    poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    poetry add --source logfire-source {package}
    ```
"""
    return re.sub(r'{{ *install_logfire\(.*\) *}}', instructions, markdown)


def install_extras_table(markdown: str, page: Page) -> str:
    """Build the table with extra installs available for logfire.

    When the markdown page has a `{{ extras_table }}` placeholder, it replaces it with a table
    listing all the extras available for logfire.

    It inspects the `pyproject.toml` file to get those extras.

    The table contains the following columns:
    - Name: The name of the extra.
    - Dependencies: The dependencies to install the extra.
    """
    if page.file.src_uri != 'install.md':
        return markdown

    with open('src/packages/logfire/pyproject.toml', mode='rb') as file:
        pyproject = tomllib.load(file)
    extras = pyproject['tool']['poetry']['extras']
    table: list[str] = []
    table.append('| Name | Dependencies |')
    table.append('| ---- | ------------ |')
    for name, deps in extras.items():
        if name == 'test':
            continue
        # Add hyperlinks to the dependencies, and </br> to wrap the lines.
        deps = '</br>'.join(f'[{dep}](https://pypi.org/project/{dep}/)' for dep in deps)
        table.append(f'| {name} | {deps} |')
        # deps = ', '.join(f'[{dep}](https://pypi.org/project/{dep}/)' for dep in deps)
        # table.append(f'| {name} | {deps} |')

    table_markdown = '\n'.join(table)
    return re.sub(r'{{ *extras_table *}}', table_markdown, markdown)
