"""The CLI for Pydantic Logfire."""

from __future__ import annotations

import argparse
import functools
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import warnings
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from operator import itemgetter
from pathlib import Path
from typing import Any, NamedTuple, cast
from urllib.parse import urlparse

import requests
from opentelemetry import trace
from rich.console import Console

from logfire.exceptions import LogfireConfigError
from logfire.propagate import ContextCarrier, get_context

from ...version import VERSION
from ..auth import HOME_LOGFIRE
from ..client import UA_HEADER, LogfireClient
from ..config import REGIONS, LogfireCredentials, get_base_url_from_token
from ..config_params import ParamManager
from ..interactive import NonInteractiveError, is_non_interactive, require_answer, set_non_interactive
from ..server_response import install_logfire_response_hook
from ..tracer import SDKTracerProvider
from ..utils import READ_TOKEN_FILENAME, ensure_data_dir_exists
from .auth import parse_auth, parse_logout
from .prompt import parse_prompt
from .run import collect_instrumentation_context, parse_run, print_otel_summary

BASE_OTEL_INTEGRATION_URL = 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/'
BASE_DOCS_URL = 'https://logfire.pydantic.dev/docs'
INTEGRATIONS_DOCS_URL = f'{BASE_DOCS_URL}/integrations/'
LOGFIRE_LOG_FILE = HOME_LOGFIRE / 'log.txt'

logger = logging.getLogger(__name__)
__all__ = 'main', 'logfire_info'


def version_callback() -> None:
    """Show the version and exit."""
    py_impl = platform.python_implementation()
    py_version = platform.python_version()
    system = platform.system()
    print(f'Running Logfire {VERSION} with {py_impl} {py_version} on {system}.')


def _parse_gateway(args: argparse.Namespace) -> None:
    """Run a local OAuth proxy for the Logfire AI Gateway."""
    from .gateway import parse_gateway

    parse_gateway(args)


def parse_whoami(args: argparse.Namespace) -> None:
    """Show user authenticated username and the URL to your Logfire project."""
    data_dir = Path(args.data_dir)
    param_manager = ParamManager.create(data_dir)
    base_url: str | None = param_manager.load_param('base_url', args.logfire_url)
    tokens = param_manager.load_param('token')

    if tokens:
        # Display info for all configured tokens
        any_succeeded = False
        for i, token in enumerate(tokens):
            if len(tokens) > 1:
                if i > 0:
                    sys.stderr.write('\n')
                sys.stderr.write(f'Token {i + 1} of {len(tokens)}:\n')
            token_base_url = base_url or get_base_url_from_token(token)
            credentials = LogfireCredentials.from_token(token, args._session, token_base_url)
            if credentials:
                credentials.print_token_summary()
                any_succeeded = True
        if any_succeeded:
            return
        # If no tokens yielded credentials, fall through to try creds file

    try:
        client = LogfireClient.from_url(base_url)
    except LogfireConfigError:
        sys.stderr.write('Not logged in. Run `logfire auth` to log in.\n')
    else:
        current_user = client.get_user_information()
        username = current_user['name']
        sys.stderr.write(f'Logged in as: {username}\n')

    credentials = _load_credentials_or_exit(data_dir)
    sys.stderr.write(f'Credentials loaded from data dir: {data_dir.resolve()}\n\n')
    credentials.print_token_summary()


def parse_clean(args: argparse.Namespace) -> None:
    """Remove the contents of the Logfire data directory."""
    files_to_delete: list[Path] = []
    if args.logs and LOGFIRE_LOG_FILE.exists():
        files_to_delete.append(LOGFIRE_LOG_FILE)

    data_dir = Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        sys.stderr.write(f'No Logfire data found in {data_dir.resolve()}\n')
        sys.exit(1)

    files_to_delete.append(data_dir / '.gitignore')
    files_to_delete.append(data_dir / 'logfire_credentials.json')
    # The saved read token is a credential too, and leaving it behind would mean a
    # "cleaned" data directory still holds something that can read the whole project.
    files_to_delete.append(data_dir / READ_TOKEN_FILENAME)

    files_to_display = '\n'.join([str(file) for file in files_to_delete if file.exists()])
    if not args.yes:
        require_answer(
            f'This would delete:\n{files_to_display}',
            'logfire clean --yes',
        )
    confirm = (
        'y' if args.yes else input(f'The following files will be deleted:\n{files_to_display}\nAre you sure? [N/y]')
    )
    if confirm.lower() in ('yes', 'y'):
        for file in files_to_delete:
            file.unlink(missing_ok=True)
        sys.stderr.write('Cleaned Logfire data.\n')
    else:
        sys.stderr.write('Clean aborted.\n')


def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend packages that might be useful."""
    console = Console(file=sys.stderr)

    ctx = collect_instrumentation_context(set(args.ignore))

    if ctx.recommendations:
        print_otel_summary(console=console, recommendations=ctx.recommendations)
        sys.exit(1)
    else:
        console.print('No recommended packages found. You are all set!', style='green')  # pragma: no cover


def parse_list_projects(args: argparse.Namespace) -> None:
    """List user projects."""
    client = LogfireClient.from_url(args.logfire_url)

    projects = sorted(client.get_user_projects(), key=itemgetter('organization_name', 'project_name'))

    if args.json:
        # stdout, so it can be piped. The human-readable table below deliberately stays on
        # stderr -- anything already parsing it keeps working, and mixing the two streams
        # would put the banner in the middle of the JSON.
        sys.stdout.write(
            json.dumps(
                [{'organization_name': p['organization_name'], 'project_name': p['project_name']} for p in projects]
            )
            + '\n'
        )
        return

    if projects:
        sys.stderr.write("List of the projects you have write access to (requires the 'write_token' permission):\n\n")
        sys.stderr.write(
            _pretty_table(
                ['Organization', 'Project'],
                [[project['organization_name'], project['project_name']] for project in projects],
            )
        )
    else:
        sys.stderr.write(
            'No projects found for the current user. You can create a new project with `logfire projects new`\n'
        )


def _write_credentials(project_info: dict[str, Any], data_dir: Path, logfire_api_url: str) -> LogfireCredentials:
    try:
        credentials = LogfireCredentials(**project_info, logfire_api_url=logfire_api_url)
        credentials.write_creds_file(data_dir)
        return credentials
    except TypeError as e:
        raise LogfireConfigError(f'Invalid credentials, when initializing project: {e}') from e


def parse_create_new_project(args: argparse.Namespace) -> None:
    """Create a new project."""
    data_dir = Path(args.data_dir)
    client = LogfireClient.from_url(args.logfire_url)

    project_name = args.project_name
    organization = args.org
    default_organization = args.default_org
    project_info = LogfireCredentials.create_new_project(
        client=client,
        organization=organization,
        default_organization=default_organization,
        project_name=project_name,
    )
    credentials = _write_credentials(project_info, data_dir, client.base_url)
    sys.stderr.write(f'Project created successfully. You will be able to view it at: {credentials.project_url}\n')


STATUS_LOOKBACK = timedelta(hours=1)
"""How far back `projects status` looks. Long enough to cover a setup session, short
enough that the answer is about what you just did rather than about last week."""

STATUS_MAX_ROWS = 10_000
"""A ceiling on the rows this asks for, so it cannot become an enormous query.

It should not bind in practice -- the result is one row per service -- but the command is
run against someone else's project and an unbounded query is not worth the surprise.
"""


def _status_sql() -> str:
    """One row per service: how much arrived and when it last did.

    Aggregated by the backend rather than by pulling rows down and counting here: a
    project with real traffic would make that unusable, and the answer (a few services) is
    far smaller than the input.

    Counts RECORDS, not spans: the table holds spans and logs together. Filtering to spans
    would be the wrong fix -- a service that only logs would then vanish from a command
    whose entire job is answering "is anything arriving from this service?". So the count
    stays inclusive and the column says what it actually is.
    """
    return (
        'SELECT service_name, count(*) AS records, max(start_timestamp) AS last_seen FROM records GROUP BY service_name'
    )


def _printable(value: object) -> str:
    """A value from telemetry, safe to write to a terminal.

    `service_name` is submitted by whoever sends the data, so it can carry ANSI escapes or
    other control characters. Written straight to stderr those can clear the screen,
    reposition the cursor, or forge lines of output in a table an operator is reading to
    decide whether their setup worked.
    """
    return ''.join(ch if ch.isprintable() or ch == ' ' else '�' for ch in str(value))


READ_TOKEN_TTL = timedelta(days=30)
"""How long a SAVED read token lasts.

Only tokens this CLI writes to disk get an expiry. The CLI cannot revoke a token, so one
sitting in a file needs some end; a token printed for the caller to paste elsewhere does
not get one, because we do not know what it was wired into and silently breaking it later
would be worse than leaving it.
"""


def _read_token_path(data_dir: Path) -> Path:
    return data_dir / READ_TOKEN_FILENAME


def _has_git_dir(start: Path) -> bool:
    """Whether `start` or any of its ancestors contains a `.git` entry.

    A pure filesystem walk, so it can tell "categorically no repository, so tracking is
    impossible" from "unconfirmed" without needing a `git` binary at all -- it walks up the
    same way `git` itself resolves a repository root from a working directory.

    Raises `OSError` (permission denied on an intermediate directory, ...) rather than
    swallowing it: the caller's whole reason for being here is telling "no repository" from
    "cannot tell", and silently returning either `True` or `False` on a filesystem error
    would collapse that distinction right back into a guess. `Path.exists()` itself
    swallows exactly that kind of error and reports `False` -- confirmed empirically, not
    merely assumed from its docs -- so this uses `lstat()` directly and treats ONLY
    `FileNotFoundError` as "confirmed absent"; every other `OSError` (permission denied, a
    path component that is not a directory, ...) propagates.
    """
    current = start.resolve()
    while True:
        try:
            (current / '.git').lstat()
        except FileNotFoundError:
            pass
        else:
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _is_git_tracked(path: Path) -> bool:
    """Whether `path` is tracked by the git repository it sits in, if any.

    `.gitignore` only stops an UNTRACKED file from being added; it does nothing for a path
    already in the index -- committed before this feature existed, or by mistake -- so
    writing a real, permanent credential through such a path would make the next `git
    commit -am` publish it.

    No `.git` anywhere in `path`'s ancestry means no git tracking anywhere either: the
    threat this guards against is categorically impossible without a repository, so that
    case is safe to treat as untracked. Checking for `.git` on disk, not merely checking
    for a `git` BINARY, matters: a repository's index is just files, and can exist -- with
    this path already tracked in it -- on a machine where `git` itself is not on `PATH`
    (uninstalled after the commit, a stripped-down `PATH` for this one subprocess call,
    etc). Trusting the binary's absence as proof of "no repository" would let exactly that
    machine state slip the write through untracked. Once a `.git` is present, though, a
    missing `git` binary is treated the same as any other failure to answer below: unconfirmed,
    not untracked.

    A `git` binary that exists but fails to answer -- the check times out, or some other
    OS-level failure -- is likewise different from a confirmed "not tracked": tracking might
    still be real, just unconfirmed, and treating that the same as "definitely untracked"
    would silently defeat this whole check on exactly the machine states an attacker aiming
    at this file is most likely to have engineered. Both cases raise, so the caller fails
    closed rather than guessing. (`git ls-files` in a directory that exists but is not a
    repository fails the SAME way a real "not tracked" answer does -- a plain non-zero exit,
    not an exception -- so that case is handled by the ordinary return below.)
    """
    if shutil.which('git') is None:
        try:
            has_repo = _has_git_dir(path.parent)
        except OSError as e:
            raise LogfireConfigError(
                f'Could not confirm whether {path} is already tracked by git (looking for a '
                f'repository above {path.parent} failed: {e}); refusing to write a live '
                f'credential through it without checking. Resolve whatever is blocking that '
                f'lookup, then try again.'
            ) from e
        if not has_repo:
            return False
        raise LogfireConfigError(
            f'Could not confirm whether {path} is already tracked by git (no `git` binary '
            f'found on PATH, but {path.parent} appears to be inside a git repository); '
            f'refusing to write a live credential through it without checking. Install git, '
            f'or resolve whatever is keeping it off PATH here, then try again.'
        )
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', '--', path.name],
            cwd=path.parent,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise LogfireConfigError(
            f'Could not confirm whether {path} is already tracked by git ({e}); refusing to '
            f'write a live credential through it without checking. Resolve whatever is '
            f'blocking `git ls-files` here, then try again.'
        ) from e
    return result.returncode == 0


def _save_read_token(
    data_dir: Path, *, token: str, base_url: str, organization: str, project_name: str, expires_at: datetime
) -> Path:
    """Write a read token into the data directory, readable only by its owner.

    The data directory already holds the write token and is gitignored (`.gitignore` of
    `*`, seeded by `ensure_data_dir_exists`), so this adds a second credential to a place
    already treated as secret rather than introducing a new one.

    `base_url` is the host the CREATE request actually used -- `client.base_url` after
    `LogfireClient.from_url(args.logfire_url)`, which comes from `--base-url`/`--region`
    flags or the user's own `~/.logfire/default.toml`, never from anything inside the
    project this command runs in. Saving it here is what lets `projects status` use it
    later without re-deriving a host from anything the repository could have tampered
    with -- see `_load_saved_read_token`.
    """
    ensure_data_dir_exists(data_dir)
    path = _read_token_path(data_dir)
    if _is_git_tracked(path):
        raise LogfireConfigError(
            f'{path} is already tracked by git, so .gitignore does not protect it. Writing '
            f'the token there risks it reaching a commit. Untrack it first '
            f'(`git rm --cached {path}`) or remove it, then try again.'
        )
    payload = {
        'token': token,
        'base_url': base_url,
        # Recorded so the token is never used for a project it was not issued for -- see
        # `_load_saved_read_token`.
        'organization': organization,
        'project_name': project_name,
        'expires_at': expires_at.isoformat(),
    }
    # O_NOFOLLOW, because this path is inside the user's repository: someone who can get a
    # symlink committed there -- or who lands one any other way -- would otherwise have
    # O_TRUNC and the mode change below applied to whatever it points at.
    # O_NOFOLLOW does not exist on Windows, where symlinks need a privilege to create.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        raise LogfireConfigError(f'Could not write the read token to {path}: {e}') from e
    try:
        # BEFORE any bytes are written. The mode passed to `os.open` applies only when it
        # creates the file, so an existing file keeps whatever permissions it had and the
        # token would land in a world-readable one, restricted only afterwards.
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, 'w')
    except BaseException:  # pragma: no cover
        # Only while the descriptor is still ours; once `fdopen` succeeds the file object
        # owns it and closing here too would be a double close.
        os.close(fd)
        raise
    with handle as f:
        json.dump(payload, f, indent=2)
        f.write('\n')
    return path


class SavedReadToken(NamedTuple):
    token: str
    # The host this token is valid against, recorded when it was created -- see
    # `_save_read_token`. Using this instead of deriving a host from the token's shape or
    # from `logfire_credentials.json` is what makes self-hosted deployments work: their
    # base URL cannot be recovered from the token, only from where it was actually minted.
    base_url: str
    # The project the token was minted for, recorded alongside it -- see `_save_read_token`.
    # Exposed so a caller with no linked project (no `logfire_credentials.json` at all) can
    # still say which project it is reporting on, using the token's own identity rather
    # than one it has no other way to name.
    organization: str
    project_name: str


def _load_saved_read_token(
    data_dir: Path, *, organization: str | None = None, project_name: str | None = None
) -> SavedReadToken | None:
    """A saved read token, if there is one and it is still usable.

    Returns None rather than raising for every failure mode -- missing, unreadable,
    corrupt, expired, belonging to a different project, or missing the host it is valid
    against. The caller turns that into one message naming the command to run, which is
    more useful than five ways to fail.

    `organization`/`project_name` given means there IS a linked project to check the token
    against, and it must match: `logfire projects use` repoints the directory, and a token
    left over from the previous project would otherwise be sent for the new one and
    produce a confusing 401 or, worse, another project's data. Omitted (both, together --
    there is no reading with only one of a project's two identifying halves) means there is
    no local link at all to check against, so the token's OWN recorded organization and
    project name are trusted directly -- read-only access should not require ever having
    held write credentials, and a saved token is already self-describing. Exactly one
    given is rejected outright: it would check the token against half a project identity,
    accepting one scoped to a same-named project in a different organization (or vice
    versa) instead of correctly falling back to trusting the token's own identity.

    Also refuses a symlink, or a file the git-tracking check from `_save_read_token` would
    have refused to write in the first place: `_save_read_token` only guards its OWN
    writes, so a `read_token.json` that arrived some other way -- committed into the repo
    by someone else, force-added, or dropped in as a symlink -- has never been through that
    check. Trusting it here would trust its `base_url` too, and that field is sent straight
    into the next request's target and `Authorization` header: an attacker who can land
    such a file controls where this command sends the token it then reads back as project
    telemetry. `_is_git_tracked` raising (tracking status unconfirmed) is treated the same
    as "tracked" here -- unlike at `_save_read_token`, failing closed on THIS call site
    means falling back to "no usable token", not blocking anything.
    """
    if (organization is None) != (project_name is None):
        return None
    path = _read_token_path(data_dir)
    if path.is_symlink():
        return None
    try:
        if _is_git_tracked(path):
            return None
    except LogfireConfigError:
        return None
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    data = cast('dict[str, Any]', raw)
    token = data.get('token')
    if not isinstance(token, str) or not token:
        return None
    base_url = data.get('base_url')
    if not isinstance(base_url, str) or not base_url:
        return None
    token_organization = data.get('organization')
    token_project_name = data.get('project_name')
    if not isinstance(token_organization, str) or not token_organization:
        return None
    if not isinstance(token_project_name, str) or not token_project_name:
        return None
    if organization is not None and token_organization != organization:
        return None
    if project_name is not None and token_project_name != project_name:
        return None
    # Absent means unbounded -- this CLI always writes the key, so a file without it was
    # written by a different version or edited by hand, and the expiry exists to bound a
    # leak rather than to gate the happy path. PRESENT but not a string is different: this
    # file always writes a string, so `null`/a number/etc. did not come from a normal run,
    # and skipping the check for it (the same way absence does) would let a tampered file
    # defeat the TTL entirely instead of just losing it. `'expires_at' in data`, not
    # `data.get('expires_at') is not None`: the key present with a JSON `null` and the key
    # truly absent both read back as `None` from `.get()`, and only one of those is fine.
    if 'expires_at' in data:
        expires_at = data['expires_at']
        if not isinstance(expires_at, str):
            return None
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
        # A naive timestamp would raise when compared against an aware one; treat it as
        # UTC, which is what this file is always written with.
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(tz=timezone.utc):
            return None
    return SavedReadToken(
        token=token, base_url=base_url, organization=token_organization, project_name=token_project_name
    )


def _load_credentials_or_exit(data_dir: Path, remedy: str | None = None) -> LogfireCredentials:
    """The project this folder is linked to, or a clean exit saying so.

    Shared with `whoami`, which had this block verbatim. `remedy` is what to run to fix
    it, for callers that know -- `whoami` deliberately passes nothing, because "you are
    not linked" is the answer it exists to give rather than a failure to recover from.
    """
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write(f'No Logfire credentials found in {data_dir.resolve()}\n')
        if remedy:
            sys.stderr.write(f'{remedy}\n')
        sys.exit(1)
    return credentials


def _organization_from_project_url(project_url: str) -> str | None:
    """The organization a project URL belongs to, or None if it does not look like one.

    The credentials file stores the project URL but not the organization, and the
    read-token endpoint needs both. Project URLs end in `<organization>/<project>`, so the
    organization is the second-to-last path segment.

    Pure, and separated out because it is the only part of `projects status` with edge
    cases worth enumerating -- a URL with no path, one segment, or a trailing slash. The
    rest of that command is I/O.
    """
    parts = [part for part in urlparse(project_url).path.split('/') if part]
    return parts[-2] if len(parts) >= 2 else None


def parse_project_status(args: argparse.Namespace) -> None:
    """Show what telemetry has reached the current project.

    Does NOT require write credentials (`logfire_credentials.json`) to exist -- only a
    saved read token, which is self-describing (it records which organization and project
    it was minted for -- see `_save_read_token`) and is all this command actually sends.
    Requiring write credentials too would mean a read-only workflow -- `read-tokens
    --project ORG/PROJECT create --save` on a directory that never ran `projects use` --
    could never use this command at all, for a linkage this command has no other need of.
    When write credentials DO exist, the saved token must still match the linked project,
    for the reason `_load_saved_read_token` documents.
    """
    data_dir = Path(args.data_dir)
    credentials = LogfireCredentials.load_creds_file(data_dir)
    saved: SavedReadToken | None
    if credentials is None:
        # Reuse the token saved next to write credentials rather than creating one here.
        # An earlier version of this command minted a read token per invocation, which is a
        # PERMANENT credential the CLI cannot revoke -- and this command is built to be run
        # repeatedly while waiting for data, so polling four times left four behind.
        saved = _load_saved_read_token(data_dir)
        if saved is None:
            sys.stderr.write(
                'No usable read token.\n'
                'Run `logfire read-tokens --project ORGANIZATION/PROJECT_NAME create --save` to create one '
                '(or run `logfire projects use PROJECT_NAME --org ORGANIZATION` first, then `logfire '
                'read-tokens create --save`), then try again.\n'
            )
            sys.exit(1)
    else:
        linked_organization = _organization_from_project_url(credentials.project_url)
        if linked_organization is None:
            sys.stderr.write(f'Cannot tell which organization {credentials.project_url} belongs to.\n')
            sys.exit(1)
        saved = _load_saved_read_token(
            data_dir, organization=linked_organization, project_name=credentials.project_name
        )
        if saved is None:
            sys.stderr.write(
                f'No usable read token for {linked_organization}/{credentials.project_name}.\n'
                'Run `logfire read-tokens create --save` to create one, then try again.\n'
            )
            sys.exit(1)

    organization = saved.organization
    project_name = saved.project_name
    # From `saved`, not `credentials.project_url`: matching organization and project name
    # does not guarantee matching HOST (self-hosted, or a different region), and the query
    # below always goes to `saved.base_url` regardless of which branch loaded `saved` --
    # this must name the same host, or the displayed URL points somewhere this command
    # never actually asked.
    project_url = f'{saved.base_url}/{organization}/{project_name}'

    # The host the token was CREATED against, not `credentials.logfire_api_url`. That field
    # comes from `logfire_credentials.json`, which lives in the project this command runs
    # inside -- a tampered repository could point it at an attacker's server and this
    # command would hand over the read token in the Authorization header of the next
    # request. An earlier version derived the host from the token's own region prefix
    # instead, which closed that hole but broke self-hosted deployments: their base URL is
    # not recoverable from the token, only from where it was actually minted, which is what
    # `saved.base_url` records -- see `_save_read_token`.
    try:
        # Over `requests`, like every other call this CLI makes. `logfire.query_client`
        # would be the obvious choice, but it needs httpx, an optional extra rather than a
        # dependency -- so using it here would break this command on a plain install.
        response = requests.post(
            f'{saved.base_url}/v2/query',
            headers={'Authorization': saved.token, 'User-Agent': UA_HEADER},
            json={
                'sql': _status_sql(),
                'min_timestamp': (datetime.now(tz=timezone.utc) - STATUS_LOOKBACK).isoformat(),
                'limit': STATUS_MAX_ROWS,
            },
            timeout=30,
        )
    except requests.RequestException as e:
        # A DNS failure, timeout, or refused connection raises here rather than returning a
        # response, and would otherwise print a raw traceback instead of this message.
        sys.stderr.write(f'Could not reach {saved.base_url}: {e}\n')
        sys.exit(1)
    # Exactly 200, not `response.ok`: a 204 or 3xx is "not an error" by that test and
    # would then fail in `.json()` with a decode error instead of this message.
    if response.status_code != 200:
        sys.stderr.write(f'Could not read the project: {response.status_code} {response.text}\n')
        sys.exit(1)
    try:
        # A 200 with a body that is not JSON, or JSON shaped unlike the query response, can
        # happen without the backend ever seeing the request -- a proxy or WAF intercepting
        # it -- and would otherwise fail below with a raw traceback instead of this message.
        raw_data: Any = response.json()['data']
        if not isinstance(raw_data, list):
            raise TypeError('"data" is not a list')
        rows = cast('list[Any]', raw_data)
        if not all(isinstance(row, dict) for row in rows):
            raise TypeError('"data" is not a list of objects')
        services = cast('list[dict[str, Any]]', rows)
    except (ValueError, KeyError, TypeError) as e:
        sys.stderr.write(f'Could not read the project: unexpected response shape ({e}).\n')
        sys.exit(1)
    services.sort(key=lambda r: str(r.get('service_name') or ''))

    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    'organization': organization,
                    'project_name': project_name,
                    'project_url': project_url,
                    'lookback_hours': STATUS_LOOKBACK.total_seconds() / 3600,
                    'services': [
                        {
                            'service_name': row.get('service_name'),
                            'records': row.get('records'),
                            'last_seen': row.get('last_seen'),
                        }
                        for row in services
                    ],
                }
            )
            + '\n'
        )
        return

    # `organization`/`project_name`/`project_url` came from a file inside the project this
    # command runs in -- write credentials or a saved read token, depending on which one
    # supplied them above (the same threat model `_save_read_token`'s docstring covers) --
    # so they get the same stripping as a service name. Not the JSON branch above, which is
    # already safe because `json.dumps` escapes control characters by construction.
    sys.stderr.write(f'Project  {_printable(organization)}/{_printable(project_name)}\n')
    sys.stderr.write(f'         {_printable(project_url)}\n\n')
    if not services:
        # Deliberately not phrased as failure. Data takes a moment to arrive, and the
        # common case for someone running this during setup is "not yet", not "broken".
        sys.stderr.write(
            f'No telemetry in the last {int(STATUS_LOOKBACK.total_seconds() // 3600)}h.\n'
            'Run the application so it sends something, then try again.\n'
        )
        return
    sys.stderr.write(
        _pretty_table(
            ['Service', 'Records', 'Last seen'],
            [
                [
                    _printable(row.get('service_name') or '(unnamed)'),
                    _printable(row.get('records') or 0),
                    _printable(row.get('last_seen') or '-'),
                ]
                for row in services
            ],
        )
    )


def parse_create_read_token(args: argparse.Namespace) -> None:
    """Create a read token for a project."""
    save: bool = getattr(args, 'save', False)
    data_dir = Path(getattr(args, 'data_dir', '.logfire'))
    organization: str | None = getattr(args, 'organization', None)
    project_name: str | None = getattr(args, 'project', None)

    if organization is None or project_name is None:
        # No `--project`, so fall back to whatever this directory is linked to. That is
        # what makes `logfire read-tokens create --save` work with no arguments at all,
        # which is the case this option exists for.
        credentials = _load_credentials_or_exit(
            data_dir,
            remedy='Pass --project <org>/<project>, or run `logfire projects use PROJECT_NAME --org ORGANIZATION` first.',
        )
        organization = organization or _organization_from_project_url(credentials.project_url)
        project_name = project_name or credentials.project_name
        if organization is None:
            sys.stderr.write(f'Cannot tell which organization {credentials.project_url} belongs to.\n')
            sys.exit(1)

    client = LogfireClient.from_url(args.logfire_url)
    expires_at = datetime.now(tz=timezone.utc) + READ_TOKEN_TTL if save else None
    response = client.create_read_token(organization, project_name, expires_at=expires_at)

    if not save:
        sys.stdout.write(response['token'] + '\n')
        return

    assert expires_at is not None
    try:
        path = _save_read_token(
            data_dir,
            token=response['token'],
            # `client.base_url` is the host the CREATE request actually used -- resolved
            # from `--base-url`/`--region` flags or the user's own `~/.logfire/default.toml`,
            # never from anything inside the project this command runs in. Recording it
            # here is what lets `projects status` reuse a trustworthy host later. Works for
            # self-hosted deployments too, since it is whatever URL the mint request was
            # really sent to.
            base_url=client.base_url,
            organization=organization,
            project_name=project_name,
            expires_at=expires_at,
        )
    except LogfireConfigError as e:
        # A symlinked destination or a read-only data directory raises here, and would
        # otherwise print a raw traceback -- worse, one AFTER a token was already minted,
        # leaving the caller unsure whether anything happened.
        sys.stderr.write(f'{e}\n')
        sys.exit(1)
    # To STDERR, and without the token. The whole point of `--save` is that the credential
    # never reaches a terminal, a log, or an agent's transcript.
    sys.stderr.write(
        f'Read token for {organization}/{project_name} saved to {path}.\n'
        f'It expires in {READ_TOKEN_TTL.days} days. `logfire projects status` will use it.\n'
    )


def parse_use_project(args: argparse.Namespace) -> None:
    """Use an existing project."""
    data_dir = Path(args.data_dir)
    client = LogfireClient.from_url(args.logfire_url)

    project_name = args.project_name
    organization = args.org
    projects = client.get_user_projects()
    project_info = LogfireCredentials.use_existing_project(
        client=client,
        projects=projects,
        organization=organization,
        project_name=project_name,
    )
    if project_info:
        credentials = _write_credentials(project_info, data_dir, client.base_url)
        sys.stderr.write(
            f'Project configured successfully. You will be able to view it at: {credentials.project_url}\n'
        )


def logfire_info() -> str:
    """Show versions of logfire, OS and related packages."""
    import importlib.metadata as importlib_metadata

    # get data about packages that are closely related to logfire
    package_names = {
        # use by otel to send data
        'requests': 1,
        # custom integration
        'pydantic': 2,
        # otel integration is customed
        'fastapi': 3,
        # custom integration
        'openai': 4,
        # dependencies of otel
        'protobuf': 5,
        # dependencies
        'rich': 6,
        # dependencies
        'typing-extensions': 7,
        # dependencies
        'tomli': 8,
        # dependencies
        'executing': 9,
    }
    otel_index = max(package_names.values(), default=0) + 1
    related_packages: list[tuple[int, str, str]] = []

    for dist in importlib_metadata.distributions():
        metadata = dist.metadata
        name = metadata.get('Name', '')
        version = metadata.get('Version', 'UNKNOWN')
        index = package_names.get(name)
        if index is not None:
            related_packages.append((index, name, version))
        if name.startswith('opentelemetry'):
            related_packages.append((otel_index, name, version))

    toml_lines: tuple[str, ...] = (
        f'logfire="{VERSION}"',
        f'platform="{platform.platform()}"',
        f'python="{sys.version}"',
        '[related_packages]',
        *(f'{name}="{version}"' for _, name, version in sorted(related_packages)),
    )
    return '\n'.join(toml_lines) + '\n'


def parse_info(_args: argparse.Namespace) -> None:
    """Show versions of logfire, OS and related packages."""
    sys.stderr.writelines(logfire_info())


def _pretty_table(header: list[str], rows: list[list[str]]):
    rows = [[' ' + first, *rest] for first, *rest in [header] + rows]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ['   | '.join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows]
    header_line = '---|-'.join('-' * width for width in widths)
    lines.insert(1, header_line)
    return '\n'.join(lines) + '\n'


def _get_logfire_url(logfire_url: str | None, region: str | None) -> str | None:
    if logfire_url is not None:
        return logfire_url
    if region is not None:
        return REGIONS[region]['base_url']


class SplitArgs(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ):
        if isinstance(values, str):  # pragma: no branch
            values = values.split(',')
        namespace_value: list[str] = getattr(namespace, self.dest) or []
        setattr(namespace, self.dest, namespace_value + list(values or []))


class OrgProjectAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ):
        if isinstance(values, str) and '/' in values:
            try:
                organization, project = values.split('/')
                if not organization or not project:
                    parser.error(f'Invalid format: {values}. Expected <org>/<project>')
                setattr(namespace, 'organization', organization)
                setattr(namespace, self.dest, project)
            except ValueError:
                parser.error(f'Invalid format: {values}. Expected <org>/<project>')
        else:
            parser.error(f'Invalid format: {values}. Expected <org>/<project>')


def _main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='logfire',
        description='The CLI for Pydantic Logfire.',
        epilog='See https://logfire.pydantic.dev/docs/reference/cli/ for more detailed documentation.',
    )

    parser.add_argument('--version', action='store_true', help='show the version and exit')
    global_opts = parser.add_argument_group(title='global options')
    global_opts.add_argument(
        '--non-interactive',
        action='store_true',
        help='never prompt; fail with guidance if an answer would be required',
    )
    url_or_region_grp = global_opts.add_mutually_exclusive_group()
    url_or_region_grp.add_argument('--logfire-url', help=argparse.SUPPRESS)
    url_or_region_grp.add_argument(
        '--base-url', help='the base URL for self-hosted Logfire instances (e.g., http://localhost:8080)'
    )
    url_or_region_grp.add_argument('--region', choices=REGIONS, help='the region to use')
    parser.set_defaults(func=lambda _: parser.print_help())  # pyright: ignore[reportUnknownLambdaType]
    subparsers = parser.add_subparsers(title='commands', metavar='')

    # NOTE(DavidM): Let's try to keep the commands listed in alphabetical order if we can
    cmd_auth = subparsers.add_parser('auth', help=parse_auth.__doc__.split('\n', 1)[0], description=parse_auth.__doc__)  # pyright: ignore[reportOptionalMemberAccess]
    cmd_auth.set_defaults(func=parse_auth)
    auth_subparsers = cmd_auth.add_subparsers()

    cmd_logout = auth_subparsers.add_parser('logout', help=parse_logout.__doc__)
    cmd_logout.set_defaults(func=parse_logout)

    cmd_clean = subparsers.add_parser('clean', help=parse_clean.__doc__)
    cmd_clean.set_defaults(func=parse_clean)
    cmd_clean.add_argument('--data-dir', default='.logfire')
    cmd_clean.add_argument('--logs', action='store_true', default=False, help='remove the Logfire logs')
    cmd_clean.add_argument('--yes', '-y', action='store_true', default=False, help='do not ask for confirmation')

    cmd_gateway = subparsers.add_parser('gateway', help=_parse_gateway.__doc__)
    cmd_gateway.add_argument('gateway_args', nargs=argparse.REMAINDER)
    cmd_gateway.set_defaults(func=_parse_gateway)

    cmd_inspect = subparsers.add_parser('inspect', help=parse_inspect.__doc__)
    cmd_inspect.set_defaults(func=parse_inspect)
    cmd_inspect.add_argument('--ignore', action=SplitArgs, default=(), help='ignore a package')

    cmd_whoami = subparsers.add_parser('whoami', help=parse_whoami.__doc__)
    cmd_whoami.set_defaults(func=parse_whoami)
    cmd_whoami.add_argument('--data-dir', default='.logfire')

    cmd_projects = subparsers.add_parser('projects', help='Project management for Logfire.')
    cmd_projects.set_defaults(func=lambda _: cmd_projects.print_help())  # pyright: ignore[reportUnknownLambdaType]
    projects_subparsers = cmd_projects.add_subparsers()

    cmd_projects_list = projects_subparsers.add_parser('list', help='list projects')
    cmd_projects_list.add_argument('--json', action='store_true', help='output JSON to stdout instead of a table')
    cmd_projects_list.set_defaults(func=parse_list_projects)

    cmd_projects_new = projects_subparsers.add_parser('new', help='create a new project')
    cmd_projects_new.add_argument('project_name', nargs='?', help='project name')
    cmd_projects_new.add_argument('--data-dir', default='.logfire')
    cmd_projects_new.add_argument('--org', help='project organization')
    cmd_projects_new.add_argument(
        '--default-org', action='store_true', help='whether to create project under user default organization'
    )
    cmd_projects_new.set_defaults(func=parse_create_new_project)

    cmd_projects_status = projects_subparsers.add_parser(
        'status', help='show what telemetry has reached the current project'
    )
    cmd_projects_status.add_argument('--data-dir', default='.logfire')
    cmd_projects_status.add_argument('--json', action='store_true', help='output JSON to stdout instead of a table')
    cmd_projects_status.set_defaults(func=parse_project_status)

    cmd_projects_use = projects_subparsers.add_parser('use', help='use a project')
    cmd_projects_use.add_argument('project_name', nargs='?', help='project name')
    cmd_projects_use.add_argument('--org', help='project organization')
    cmd_projects_use.add_argument('--data-dir', default='.logfire')
    cmd_projects_use.set_defaults(func=parse_use_project)

    cmd_read_tokens = subparsers.add_parser('read-tokens', help='Manage read tokens for a project')
    cmd_read_tokens.add_argument('--project', action=OrgProjectAction, help='project in the format <org>/<project>')
    # `OrgProjectAction` only sets `organization` when `--project` is given, so without a
    # default the attribute is missing entirely and reading it raises `AttributeError`.
    cmd_read_tokens.set_defaults(func=lambda _: cmd_read_tokens.print_help(), organization=None)  # pyright: ignore[reportUnknownLambdaType]
    read_tokens_subparsers = cmd_read_tokens.add_subparsers()

    # With this command you can do:
    # claude mcp add logfire -e LOGFIRE_READ_TOKEN=$(logfire read-tokens --project kludex/potato create) -- uvx logfire-mcp@latest
    cmd_read_tokens_create = read_tokens_subparsers.add_parser('create', help=parse_create_read_token.__doc__)
    cmd_read_tokens_create.add_argument(
        '--save',
        action='store_true',
        help='save the token into the data directory instead of printing it, for `logfire projects status`',
    )
    cmd_read_tokens_create.add_argument('--data-dir', default='.logfire')
    cmd_read_tokens_create.set_defaults(func=parse_create_read_token)

    cmd_prompt = subparsers.add_parser('prompt', help=parse_prompt.__doc__)
    agent_code_argument_group = cmd_prompt.add_argument_group(title='code agentic specific options')
    agent_code_group = agent_code_argument_group.add_mutually_exclusive_group()
    agent_code_group.add_argument('--claude', action='store_true', help='verify the Claude Code setup')
    agent_code_group.add_argument('--codex', action='store_true', help='verify the Cursor setup')
    agent_code_group.add_argument('--opencode', action='store_true', help='verify the OpenCode setup')
    cmd_prompt.add_argument(
        '--update', action='store_true', help='replace any existing Logfire MCP server configuration'
    )
    cmd_prompt.add_argument('--project', action=OrgProjectAction, help='project in the format <org>/<project>')
    cmd_prompt.add_argument('issue', nargs='?', help='the issue to get a prompt for')
    cmd_prompt.set_defaults(func=parse_prompt)

    cmd_info = subparsers.add_parser('info', help=parse_info.__doc__)
    cmd_info.set_defaults(func=parse_info)

    cmd_run = subparsers.add_parser('run', help='Run Python scripts/modules with Logfire instrumentation')
    cmd_run.add_argument('--summary', action=argparse.BooleanOptionalAction, default=True, help='hide the summary box')
    cmd_run.add_argument('--exclude', action=SplitArgs, default=(), help='exclude a package from instrumentation')
    cmd_run.add_argument('-m', '--module', help='Run module as script')
    cmd_run.add_argument(
        'script_and_args', nargs=argparse.REMAINDER, help='Script path and arguments, or module arguments when using -m'
    )
    cmd_run.set_defaults(func=parse_run)

    # We first try to parse everything, and if it's not the `parse_run` command, we parse again to raise an error on
    # unknown args. This is to allow the `parse_run` command to forward unknown args to the script/module.
    namespace, unknown_args = parser.parse_known_args(args)
    if namespace.func == parse_run:
        namespace.script_and_args = unknown_args + (namespace.script_and_args or [])
    else:
        namespace = parser.parse_args(args)
    set_non_interactive(namespace.non_interactive)

    if namespace.logfire_url:
        warnings.warn(
            'The `--logfire-url` argument is deprecated. Use `--base-url` instead.',
            DeprecationWarning,
            stacklevel=2,
        )

    namespace.logfire_url = namespace.logfire_url or namespace.base_url
    namespace.logfire_url = _get_logfire_url(namespace.logfire_url, namespace.region)

    trace.set_tracer_provider(tracer_provider=SDKTracerProvider())
    tracer = trace.get_tracer(__name__)

    def log_trace_id(response: requests.Response, context: ContextCarrier, *args: Any, **kwargs: Any) -> None:
        logger.debug('context=%s url=%s', context, response.url)

    if namespace.version:
        version_callback()
    elif namespace.func in (parse_info, parse_run):
        namespace.func(namespace)
    else:
        with tracer.start_as_current_span('logfire._internal.cli'), requests.Session() as session:
            context = get_context()
            session.hooks = {'response': [functools.partial(log_trace_id, context=context)]}
            session.headers.update(context)
            install_logfire_response_hook(session)
            namespace._session = session
            namespace.func(namespace)


def main(args: list[str] | None = None) -> None:
    """Run the CLI."""
    HOME_LOGFIRE.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(LOGFIRE_LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    logging.basicConfig(handlers=[file_handler], level=logging.DEBUG)

    previous_non_interactive = is_non_interactive()
    try:
        _main(args)
    except KeyboardInterrupt:
        sys.stderr.write('User cancelled.\n')
        sys.exit(1)
    except NonInteractiveError as e:
        # The whole point is guidance instead of a traceback, so it must not escape.
        sys.stderr.write(f'{e}\n')
        sys.exit(1)
    finally:
        # Restore rather than clear: `main()` is importable and an application may call it
        # in-process, where leaving the switch set would silently stop every later prompt
        # -- including ones in `logfire.configure()`, which this flag does not govern.
        set_non_interactive(previous_non_interactive)
        file_handler.close()
