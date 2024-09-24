from __future__ import annotations as _annotations

import re
import subprocess
from pathlib import Path

from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from logfire._internal import config_params, metrics

LOGFIRE_DIR = Path(__file__).parent.parent.parent


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """
    Called on each file after it is read and before it is converted to HTML.
    """
    markdown = build_environment_variables_table(markdown, page)
    markdown = logfire_print_help(markdown, page)
    markdown = install_logfire(markdown, page)
    markdown = check_documented_system_metrics(markdown, page)
    markdown = warning_on_third_party(markdown, page)
    return markdown


def check_documented_system_metrics(markdown: str, page: Page) -> str:
    """Check that all system metrics are documented.

    The system metrics are the ones defined in `logfire._metrics.DEFAULT_CONFIG`.

    The documentation is in `metrics.md`. The metrics are documented in bullet points, like this:
    * `system.cpu.time`: The CPU time spent in different modes.
    * `system.cpu.utilization`: The CPU utilization in different modes.

    This function checks that all the metrics in `DEFAULT_CONFIG` are documented.
    """
    if page.file.src_uri != 'guides/onboarding_checklist/06_add_metrics.md':
        return markdown

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
    # if you don't filter to the specific route that needs this substitution, things will be very slow
    if page.file.src_uri != 'reference/cli.md':
        return markdown

    output = subprocess.run(['logfire', '--help'], capture_output=True, check=True)
    logfire_help = output.stdout.decode()
    return re.sub(r'{{ *logfire_help *}}', logfire_help, markdown)


def build_environment_variables_table(markdown: str, page: Page) -> str:
    """Build the environment variables table for the configuration page.

    Check http://127.0.0.1:8000/configuration/#using-environment-variables.
    """
    if page.file.src_uri != 'reference/configuration.md':
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
    if not (
        page.file.src_uri.startswith('integrations/')
        or page.file.src_uri == 'index.md'
        or page.file.src_uri.endswith('onboarding_checklist/add_metrics.md')
    ):
        return markdown

    # Match instructions like "{{ install_logfire(extras=['fastapi']) }}". Get the extras, if any.
    matches = re.findall(r'{{ *install_logfire\((.*)\) *}}', markdown)
    extras = []
    for match in matches:
        arguments = match.split('=')
        # Split them and strip quotes for each one separately.
        extras = [arg.strip('\'"') for arg in arguments[1].strip('[]').split(',')] if len(arguments) > 1 else []
        package = 'logfire' if not extras else f"'logfire[{','.join(extras)}]'"
        # Hiding unused arg because the linter is yelling at me
        #  extras_arg = ' '.join(f'-E {extra}' for extra in extras)
        instructions = f"""
=== "pip"
    ```bash
    pip install {package}
    ```

=== "uv"
    ```bash
    uv add {package}
    ```
"""
        if not extras:
            instructions += """

=== "rye"
    ```bash
    rye add logfire {extras_arg}
    ```

=== "poetry"
    ```bash
    poetry add {package}
    ```

=== "conda"
    ```bash
    conda install -c conda-forge logfire
    ```
"""
        markdown = re.sub(r'{{ *install_logfire\(.*\) *}}', instructions, markdown, count=1)
    return markdown


def warning_on_third_party(markdown: str, page: Page) -> str:
    uri = page.file.src_uri
    if uri == 'integrations/third_party/index.md' or not uri.startswith('integrations/third_party/'):
        return markdown

    note = """
!!! note "Third-party integrations"
    Third-party integrations are not officially supported by **Logfire**.

    They are maintained by the community and may not be as reliable as the integrations developed by **Logfire**.
"""

    return note + markdown
