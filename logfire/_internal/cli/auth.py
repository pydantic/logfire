from __future__ import annotations

import argparse
import sys
import webbrowser
from urllib.parse import urlparse

from ...exceptions import LogfireConfigError
from ..auth import DEFAULT_FILE, UserTokenCollection, poll_for_token, request_device_code
from ..config import REGIONS
from ..interactive import is_non_interactive, require_answer


def _read_line(prompt: str = '') -> str | None:
    """Read one line of input, or `None` if there is nothing there to read.

    Deliberately not `sys.stdin.isatty()`. That answers "is a terminal attached", which is
    a different question: a pipe is not a tty and is perfectly answerable, and
    piping the answers in is how scripts have always driven this command. Gating on
    isatty() would turn that into a hard failure.

    `sys.stdin` can also be None (pythonw, some embedded runtimes), where `input()` raises
    `RuntimeError('lost sys.stdin')`, and reading a closed stream raises `ValueError`.
    All of them mean the same thing here: no answer is available.
    """
    try:
        return input(prompt)
    except (EOFError, RuntimeError, AttributeError, ValueError):
        return None


def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This will authenticate your machine with Logfire and store the credentials.
    """
    logfire_url: str | None = args.logfire_url

    tokens_collection = UserTokenCollection()
    logged_in = tokens_collection.is_logged_in(logfire_url)

    if logged_in:
        sys.stderr.writelines(
            (
                f'You are already logged in. (Your credentials are stored in {DEFAULT_FILE})\n',
                'If you would like to log in using a different account, use the --region argument:\n',
                'logfire --region <region> auth\n',
            )
        )
        return

    sys.stderr.writelines(
        (
            '\n',
            'Welcome to Logfire! 🔥\n',
            'Before you can send data to Logfire, we need to authenticate you.\n',
            '\n',
        )
    )
    if not logfire_url:
        require_answer(
            'Logfire is available in multiple data regions and no region was selected.',
            *(f'logfire --region {region_id} auth' for region_id in REGIONS),
        )
        selected_region = -1
        while not (1 <= selected_region <= len(REGIONS)):
            sys.stderr.write('Logfire is available in multiple data regions. Please select one:\n')
            for i, (region_id, region_data) in enumerate(REGIONS.items(), start=1):
                sys.stderr.write(f'{i}. {region_id.upper()} (GCP region: {region_data["gcp_region"]})\n')

            answer = _read_line(f'Selected region [{"/".join(str(i) for i in range(1, len(REGIONS) + 1))}]: ')
            if answer is None:
                # Nothing to read and nothing to guess from: which region holds your data
                # is not ours to pick. It is answerable ahead of time, and saying so beats
                # looping forever or raising EOFError from a prompt nobody can reply to.
                #
                # Written and exited rather than raised: an exception escapes `main()`,
                # which catches only KeyboardInterrupt, so the caller gets a traceback --
                # which is the thing this change set out to remove. Each region is spelled
                # out as its own runnable line, because `--region us|eu` is a shell
                # pipeline if you paste it.
                sys.stderr.write(
                    'Logfire is available in multiple data regions and no region was selected.\n'
                    'Re-run in an interactive terminal to choose, or pass one:\n'
                )
                for region_id in REGIONS:
                    sys.stderr.write(f'  logfire --region {region_id} auth\n')
                sys.exit(1)
            try:
                selected_region = int(answer)
            except ValueError:
                selected_region = -1
        logfire_url = list(REGIONS.values())[selected_region - 1]['base_url']

    device_code, frontend_auth_url = request_device_code(args._session, logfire_url)
    frontend_host = urlparse(frontend_auth_url).netloc

    # This prompt exists to give a person a beat before a browser window appears. When
    # there is no one to press the key -- CI, a container, a coding agent -- there is no
    # beat to give and no browser to open, and BLOCKING on it turned the whole command
    # into an EOFError traceback for every such caller.
    #
    # Nothing else about the flow needs a terminal: the URL is printed below and the
    # device-code poll simply waits, so a caller can surface the link and the login
    # completes when the user opens it.
    #
    # `--non-interactive` is checked BEFORE reading rather than relying on the read
    # failing, because a read is exactly what it cannot afford: with `--region` supplied
    # the region prompt is skipped and this is the next stop, so an open, silent stdin
    # hung here -- the precise failure the flag exists to prevent.
    if not is_non_interactive():
        # We are not using the `prompt` parameter from `input` here because we want to write to stderr.
        sys.stderr.write(f'Press Enter to open {frontend_host} in your browser...\n')
        if _read_line() is not None:
            try:
                webbrowser.open(frontend_auth_url, new=2)
            except webbrowser.Error:
                pass
    sys.stderr.writelines(
        (
            f"Please open {frontend_auth_url} in your browser to authenticate if it hasn't already.\n",
            'Waiting for you to authenticate with Logfire...\n',
        )
    )

    tokens_collection.add_token(logfire_url, poll_for_token(args._session, device_code, logfire_url))
    sys.stderr.write('Successfully authenticated!\n')
    sys.stderr.write(f'\nYour Logfire credentials are stored in {DEFAULT_FILE}\n')


def parse_logout(args: argparse.Namespace) -> None:
    """Log out from Logfire."""
    logfire_url: str | None = args.logfire_url

    tokens_collection = UserTokenCollection()

    try:
        removed = tokens_collection.logout(logfire_url)
    except LogfireConfigError as e:
        sys.stderr.write(f'{e}\n')
        sys.exit(1)

    for url in removed:
        sys.stderr.write(f'Successfully logged out from {url}\n')
    sys.stderr.write(f'\nYour Logfire credentials have been removed from {DEFAULT_FILE}\n')
