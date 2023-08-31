import hashlib
import os
import sys
from pathlib import Path
from typing import Callable

from platformdirs import user_config_dir
from pydantic import BaseModel, ValidationError


class LogfireCredentials(BaseModel):
    project_id: str
    token: str


def get_credentials_file(
    storage_root: Path | None = None,
    interpreter: bool = True,
    cwd: bool = False,
    script: bool = False,
) -> Path:
    """Generate a path to store a generated secret in for easy reuse."""
    hash_object = hashlib.sha256()
    if interpreter:
        hash_object.update(sys.executable.encode())
    if cwd:
        hash_object.update(os.getcwd().encode())
    if script:
        hash_object.update(sys.argv[0].encode())

    credentials_key = hash_object.hexdigest()

    return (storage_root or Path(user_config_dir('logfire'))) / f'credentials-{credentials_key}.json'


def get_credentials(
    project_id: str | None,
    token: str | None,
    credentials_file: Path,
    request_credentials: Callable[[str | None], LogfireCredentials],
) -> LogfireCredentials:
    # TODO(DavidM): Do something smarter than print logging in this function

    # If the token is explicitly specified, the project_id must also be
    if token is not None:
        if project_id is not None:
            # Note: if both project_id and token are explicitly specified, the credentials_file is ignored
            return LogfireCredentials(project_id=project_id, token=token)
        else:
            raise ValueError('If the token is explicitly specified, the project_id must be as well.')

    # The token was not specified in environment; try to load the project ID and token from the credentials file
    if credentials_file.is_file():
        content = credentials_file.read_text()
        try:
            creds = LogfireCredentials.model_validate_json(content)
        except ValidationError as e:
            raise ValueError(
                f'Invalid credentials file: {credentials_file}. Delete the file to clear this error.'
            ) from e
        else:
            print(f'Using credentials loaded from {credentials_file}')
            # If the credentials file exists _and_ a project_id was explicitly specified, error if they don't match:
            if project_id is not None and creds.project_id != project_id:
                raise ValueError(
                    f'Project ID mismatch:'
                    f' {creds.project_id!r} (from credentials file) != {project_id!r} (explicitly specified).'
                    f' Delete the credentials file or explicitly specify the token to clear this error.'
                )
            return creds

    # No credentials file was present, so hit the project creation endpoint
    creds = request_credentials(project_id)

    # Store the credentials in the credentials file
    credentials_file.parent.mkdir(parents=True, exist_ok=True)
    credentials_file.write_text(creds.model_dump_json(indent=2))
    print(f'New logfire project created with project_id={creds.project_id!r}')
    print(f'Credentials stored in {credentials_file}')
    return creds
