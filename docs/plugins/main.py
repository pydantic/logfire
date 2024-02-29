from __future__ import annotations as _annotations

import re
import subprocess
from pathlib import Path

import tomllib
from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from logfire import _config_params as config_params, _metrics as metrics

LOGFIRE_DIR = Path(__file__).parent.parent.parent


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """
    Called on each file after it is read and before it is converted to HTML.
    """
    markdown = build_environment_variables_table(markdown, page)
    markdown = logfire_print_help(markdown, page)
    markdown = install_logfire(markdown, page)
    markdown = install_extras_table(markdown, page)
    if page.file.src_uri == 'metrics.md':
        check_documented_system_metrics(markdown, page)
    return markdown


def check_documented_system_metrics(markdown: str, page: Page) -> str:
    """Check that all system metrics are documented.

    The system metrics are the ones defined in `logfire._metrics.DEFAULT_CONFIG`.

    The documentation is in `metrics.md`. The metrics are documented in bullet points, like this:
    * `system.cpu.time`: The CPU time spent in different modes.
    * `system.cpu.utilization`: The CPU utilization in different modes.

    This function checks that all the metrics in `DEFAULT_CONFIG` are documented.
    """
    metrics_documented: set[str] = set()
    for line in markdown.splitlines():
        match = re.search(r'\* `(.*)`: ', line)
        if match:
            metrics_documented.add(match.group(1))

    # Check that all the metrics are documented.
    for metric in metrics.DEFAULT_CONFIG:
        if metric not in metrics_documented:
            raise RuntimeError(f'Metric {metric} is not documented on the metrics page.')

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
    if not (page.file.src_uri.startswith('integrations/') or page.file.src_uri == 'install.md'):
        return markdown

    # Match instructions like "{{ install_logfire(extras=['fastapi']) }}". Get the extras, if any.
    match = re.search(r'{{ *install_logfire\((.*)\) *}}', markdown)
    extras = []
    if match:
        arguments = match.group(1).split('=')
        extras = arguments[1].strip('[]').strip('\'"').split(',') if len(arguments) > 1 else []

    # Build the installation instructions.
    package = 'logfire' if not extras else f"'logfire[{','.join(extras)}]'"
    instructions = f"""
=== "PIP"
    ```bash
    pip install {package}
    ```

=== "Poetry"
    ```bash
    poetry add {package}
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

    with (LOGFIRE_DIR / 'pyproject.toml').open(mode='rb') as file:
        pyproject = tomllib.load(file)
    extras = pyproject['tool']['poetry']['extras']
    table: list[str] = []
    table.append('| Name | Dependencies |')
    table.append('| ---- | ------------ |')
    for name, deps in extras.items():
        if name == 'test':
            continue
        # Add hyperlinks to the dependencies, and join them with a pipe.
        deps = ' \| '.join(f'[{dep}](https://pypi.org/project/{dep}/)' for dep in deps)
        integration_md = f'integrations/{name}.md'
        if name == 'system-metrics':
            integration_md = 'usage/metrics.md'
        table.append(f'| [{name}]({integration_md}) | {deps} |')

    table_markdown = '\n'.join(table)
    return re.sub(r'{{ *extras_table *}}', table_markdown, markdown)
