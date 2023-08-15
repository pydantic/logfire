import hashlib
import os
import secrets
import socket
import sys
import tempfile
import uuid
from pathlib import Path


def get_secret_storage_path(
    storage_root: Path | None = None,
    host: bool = True,
    interpreter: bool = True,
    cwd: bool = False,
    script: bool = False,
) -> Path:
    """Generate a path to store a generated secret in for easy reuse."""
    hash_object = hashlib.sha256()
    if host:
        hash_object.update(socket.gethostname().encode())
    if interpreter:
        hash_object.update(sys.executable.encode())
    if cwd:
        hash_object.update(os.getcwd().encode())
    if script:
        hash_object.update(sys.argv[0].encode())

    storage_root = storage_root or Path(tempfile.gettempdir())

    return storage_root / f'{hash_object.hexdigest()}.txt'


def get_or_generate_secret(path: Path | None = None, reset: bool = False, verbose: bool = False) -> str:
    """Currently, I assume that the "secret" is actually a UUID, and will be placed directly into the URL.

    This means that if you know the URL for observing, you have the secret necessary to send data.

    While in principle this presents a security concern, it removes a bit of complexity to get started trying things
    out (which I suspect is a good thing for initial user experience), and may push people away from the "free tier"
    sooner.

    If this is more of a negative than a positive, we could change this at any time by using the hash of the secret in
    the URL instead of the secret itself, or by having two secrets — one for reading (and/or inclusion in the URL), and
    a separate one for writing.
    """
    path = path or get_secret_storage_path()

    if path.is_file() and not reset:
        if verbose:
            print(f'Using secret stored in: {path}')
        secret = path.read_text().strip()
    else:
        secret = str(uuid.UUID(bytes=secrets.token_bytes(16)))
        # Note: Could do something where we require the hash be below a specified threshold to
        # make it harder to generate secrets collisions, etc.

        if verbose:
            print(f'Storing secret in: {path}')
        path.write_text(secret)

    return secret
