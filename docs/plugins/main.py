from __future__ import annotations as _annotations

import re
import subprocess
from pathlib import Path

from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from logfire._internal import config_params

LOGFIRE_DIR = Path(__file__).parent.parent.parent


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """
    Called on each file after it is read and before it is converted to HTML.
    """
    markdown = build_environment_variables_table(markdown, page)
    markdown = logfire_print_help(markdown, page)
    markdown = install_logfire(markdown, page)
    markdown = integrations_metadata(markdown, page)
    markdown = footer_web_frameworks(markdown, page)
    return markdown


def on_files(files: Files, config: Config) -> None:
    for file in files:
        if file.src_path.endswith('.md') and '_' in file.src_uri:
            raise RuntimeError(
                f'File {file.src_path} contains an underscore. '
                'For SEO reasons, the file should not contain underscores.'
            )


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
        or page.file.src_uri.endswith('onboarding-checklist/add-metrics.md')
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
        instructions = [
            '=== "pip"',
            '    ```bash',
            f'    pip install {package}',
            '    ```',
            '=== "uv"',
            '    ```bash',
            f'    uv add {package}',
            '    ```',
            '=== "poetry"',
            '    ```bash',
            f'    poetry add {package}',
            '    ```',
        ]

        if not extras:
            instructions.extend(['=== "conda"', '    ```bash', '    conda install -c conda-forge logfire', '    ```'])
        instructions_str = '\n'.join(instructions)

        def replace_match(match: re.Match[str]) -> str:
            indent = match.group('indent')
            return indent + instructions_str.replace('\n', '\n' + indent)

        markdown = re.sub(r'(?P<indent> *){{ *install_logfire\(.*\) *}}', replace_match, markdown, count=1)
    return markdown


def warning_on_third_party(markdown: str, page: Page) -> str:
    note = """
!!! note "Third-party integrations"
    Third-party integrations are not officially supported by **Logfire**.

    They are maintained by the community and may not be as reliable as the integrations developed by **Logfire**.
"""

    return note + markdown


def integrations_metadata(markdown: str, page: Page) -> str:
    if not page.file.src_uri.startswith('integrations/') or 'index.md' in page.file.src_uri:
        return markdown

    integration = page.meta.get('integration')
    if integration is None:
        raise RuntimeError(f"""
            The page {page.file.src_uri} is missing the "integration" metadata.
            Add the metadata to the page like this:
            ```yaml
            integration: custom
            ```
            The value can be "logfire", "third-party", "built-in" or "otel".
        """)
    if integration == 'third-party':
        markdown = warning_on_third_party(markdown, page)
    return markdown


otel_docs = {
    'flask': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html',
    'fastapi': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html',
    'django': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html',
    'starlette': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html',
    'asgi': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html',
    'wsgi': 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html',
}


def footer_web_frameworks(markdown: str, page: Page) -> str:
    if not page.file.src_uri.startswith('integrations/web-frameworks/') or page.file.src_path.endswith('index.md'):
        return markdown
    exclude_lists = """
## Excluding URLs from instrumentation

- [Quick guide](../web-frameworks/index.md#excluding-urls-from-instrumentation)
"""
    if page.file.name == 'asgi':
        exclude_lists += """

!!! note
    `instrument_asgi` does accept an `excluded_urls` parameter, but does not support specifying said URLs via an environment variable,
    unlike other instrumentations.
"""
    elif not page.file.name == 'wsgi':
        exclude_lists += f"""
- [OpenTelemetry Documentation]({otel_docs[page.file.name]}#exclude-lists)
"""
    capture_headers = f"""
## Capturing request and response headers

- [Quick guide](../web-frameworks/index.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation]({otel_docs[page.file.name]}#capture-http-request-and-response-headers)
"""
    return markdown + exclude_lists + capture_headers
