"""Secure storage for OAuth access and refresh tokens.

Keyring-first, file-fallback strategy following RFC 8252 / RFC 9700 guidance and
mirroring the behavior of tools like `gh auth` and `pup`:

- When the OS keyring is available (macOS Keychain, Linux Secret Service, Windows
  Credential Locker), the access_token and refresh_token live in the keyring and
  only non-secret metadata is persisted to `~/.logfire/default.toml`.
- When the keyring is unavailable (not installed, no backend, headless CI, ...),
  the tokens are stored inline in the same TOML file with permissions set to 0600.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_keyring_module: Any = None
_keyring_error: type[Exception] = Exception
_keyring_import_ok = False

try:
    import keyring as _keyring_module
    from keyring.errors import KeyringError as _KeyringError

    _keyring_error = _KeyringError
    _keyring_import_ok = True
except ImportError:
    pass


KEYRING_SERVICE = 'logfire-oauth'
"""Service name used when storing tokens in the OS keyring."""


@dataclass
class StoredOAuthSecrets:
    """Secret material for an OAuth login (kept out of TOML when possible)."""

    access_token: str
    refresh_token: str


class TokenStorage:
    """Keyring-first, file-fallback persistence of OAuth access/refresh tokens.

    The class is stateless — each call probes the keyring on demand and degrades
    gracefully if it is unavailable. Metadata persistence (scope, expiration,
    client_id) lives in the regular token TOML file; this class only owns the
    secret material.
    """

    def __init__(self) -> None:
        self._use_keyring: bool | None = None

    @property
    def keyring_available(self) -> bool:
        """Whether the keyring backend is importable and functional."""
        if self._use_keyring is None:
            self._use_keyring = self._probe_keyring()
        return self._use_keyring

    def _probe_keyring(self) -> bool:
        if not _keyring_import_ok or _keyring_module is None:
            return False
        try:
            _keyring_module.get_password(KEYRING_SERVICE, '__logfire_probe__')
        except _keyring_error:
            sys.stderr.write(
                'Warning: system keyring is unavailable; OAuth tokens will be stored in ~/.logfire/default.toml instead.\n'
            )
            return False
        except Exception:
            # Unexpected backend error — never let storage probing crash the CLI.
            return False
        return True

    def save(self, base_url: str, secrets: StoredOAuthSecrets) -> bool:
        """Store tokens for `base_url` in the keyring.

        Returns True on success, False if the keyring is unavailable (the caller
        should then fall back to inline TOML storage).
        """
        if not self.keyring_available or _keyring_module is None:
            return False
        try:
            _keyring_module.set_password(
                KEYRING_SERVICE,
                base_url,
                json.dumps({'access_token': secrets.access_token, 'refresh_token': secrets.refresh_token}),
            )
        except _keyring_error as e:
            sys.stderr.write(f'Warning: failed to save OAuth token to system keyring ({e}); falling back to file.\n')
            return False
        return True

    def load(self, base_url: str) -> StoredOAuthSecrets | None:
        """Return tokens stored for `base_url`, or None if keyring has no entry."""
        if not self.keyring_available or _keyring_module is None:
            return None
        try:
            raw = _keyring_module.get_password(KEYRING_SERVICE, base_url)
        except _keyring_error:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        access = data.get('access_token')
        refresh = data.get('refresh_token')
        if not access or not refresh:
            return None
        return StoredOAuthSecrets(access_token=access, refresh_token=refresh)

    def delete(self, base_url: str) -> None:
        """Best-effort deletion of tokens for `base_url` from the keyring."""
        if not self.keyring_available or _keyring_module is None:
            return
        try:
            _keyring_module.delete_password(KEYRING_SERVICE, base_url)
        except _keyring_error:
            pass


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Acquire an exclusive, cross-platform advisory lock on `path` (blocking).

    Used to serialize refresh-token exchanges across concurrent `logfire`
    processes sharing the same `~/.logfire/default.toml`. A dedicated `.lock`
    sibling file is used so that truncating/rewriting the TOML file cannot
    invalidate the lock handle.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + '.lock')
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    locked = False
    try:
        _acquire_lock(fd)
        locked = True
        yield
    finally:
        if locked:
            _release_lock(fd)
        os.close(fd)


def _acquire_lock(fd: int) -> None:
    if os.name == 'nt':  # pragma: no cover
        import msvcrt

        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                return
            except OSError:
                # `LK_LOCK` retries internally for ~10s but can still time out;
                # re-issue it so we wait until the lock is actually free.
                continue
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _release_lock(fd: int) -> None:
    if os.name == 'nt':  # pragma: no cover
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
