from __future__ import annotations as _annotations

import os
import threading
import warnings
import weakref
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

from opentelemetry.util._once import Once
from pydantic import ValidationError
from requests import Session

from logfire._internal.client import UA_HEADER
from logfire._internal.config import RemoteVariablesConfig
from logfire._internal.utils import UnexpectedResponse
from logfire.variables.abstract import ResolvedVariable, VariableProvider
from logfire.variables.config import VariablesConfig

__all__ = ('LogfireRemoteVariableProvider',)


class LogfireRemoteVariableProvider(VariableProvider):
    """Variable provider that fetches configuration from a remote Logfire API.

    The threading implementation draws heavily from opentelemetry.sdk._shared_internal.BatchProcessor.
    """

    def __init__(self, base_url: str, token: str, config: RemoteVariablesConfig):
        """Create a new remote variable provider.

        Args:
            base_url: The base URL of the Logfire API.
            token: Authentication token for the Logfire API.
            config: Config for retrieving remote variables.
        """
        super().__init__()

        block_before_first_resolve = config.block_before_first_resolve
        polling_interval = config.polling_interval

        self._base_url = base_url
        self._session = Session()
        self._session.headers.update({'Authorization': f'bearer {token}', 'User-Agent': UA_HEADER})
        self._block_before_first_fetch = block_before_first_resolve
        self._polling_interval: timedelta = (
            timedelta(seconds=polling_interval) if isinstance(polling_interval, float | int) else polling_interval
        )

        self._reset_once = Once()
        self._has_attempted_fetch: bool = False
        self._last_fetched_at: datetime | None = None

        self._config: VariablesConfig | None = None
        self._worker_thread = threading.Thread(
            name='LogfireRemoteProvider',
            target=self._worker,
            daemon=True,
        )

        self._shutdown = False
        self._shutdown_timeout_exceeded = False
        self._refresh_lock = threading.Lock()
        self._worker_awaken = threading.Event()
        self._worker_thread.start()
        if hasattr(os, 'register_at_fork'):
            weak_reinit = weakref.WeakMethod(self._at_fork_reinit)
            os.register_at_fork(after_in_child=lambda: weak_reinit()())  # pyright: ignore[reportOptionalCall]
        self._pid = os.getpid()

    def _at_fork_reinit(self):
        # Recreate all things threading related
        self._refresh_lock = threading.Lock()
        self._worker_awaken = threading.Event()
        self._worker_thread = threading.Thread(
            name='LogfireRemoteProvider',
            target=self._worker,
            daemon=True,
        )
        self._worker_thread.start()
        self._pid = os.getpid()

    def _worker(self):
        while not self._shutdown:
            # Note: Ideally we'd be able to terminate while the following request was going even if it takes a while,
            # it's far more reasonable to terminate this worker thread "gracelessly" than an OTel exporter's.
            # But given this is pretty unlikely to cause issues, Alex and I decided are okay leaving this as-is.
            # We can change this if we run into issues, but it doesn't seem to be causing any now.
            self.refresh()
            self._worker_awaken.clear()
            self._worker_awaken.wait(self._polling_interval.total_seconds())
            if self._shutdown:
                break

    def refresh(self, force: bool = False):
        """Fetch the latest variable configuration from the remote API.

        Args:
            force: If True, fetch configuration even if the polling interval hasn't elapsed.
        """
        if self._refresh_lock.locked():
            # If we're already fetching, we'll get a new value, so no need to force
            force = False

        # TODO: Probably makes sense to replace this with something that just polls for a version number or hash
        #   or similar, rather than the whole config, and only grabs the whole config if that version or hash changes.
        with self._refresh_lock:  # Make at most one request at a time
            # TODO: Do we need to rethink how the force-refreshing works?
            #   Right now if you tried to force-refresh multiple times in parallel,
            #   it would jankily do all the requests in serial... this is presumably rare but still feels like bad implementation?
            if (
                not force
                and self._last_fetched_at is not None
                and self._last_fetched_at > datetime.now(tz=timezone.utc) - self._polling_interval
            ):
                return  # nothing to do

            try:
                variables_response = self._session.get(urljoin(self._base_url, '/v1/variables/'))
                UnexpectedResponse.raise_for_status(variables_response)
            except UnexpectedResponse:
                # TODO: Update the following logic to be smarter
                # TODO: Handle any error here, not just UnexpectedResponse, so we don't crash user application on failure
                warnings.warn('Error retrieving variables', category=RuntimeWarning)
                return

            variables_config_data = variables_response.json()
            try:
                self._config = VariablesConfig.validate_python(variables_config_data)
            except ValidationError as e:
                # TODO: Update the following logic to be smarter
                warnings.warn(str(e), category=RuntimeWarning)
            finally:
                self._has_attempted_fetch = True

            # TODO: Should we set `_last_fetched_at` even on failure?
            self._last_fetched_at = datetime.now(tz=timezone.utc)

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Resolve a variable's serialized value from the remote configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
        """
        if self._pid != os.getpid():
            self._reset_once.do_once(self._at_fork_reinit)

        if not self._has_attempted_fetch and self._block_before_first_fetch:
            # Block while waiting for the request to be sent
            # TODO: Should we have an async version of this method that doesn't block the event loop?
            #   Note that we could add a force_refresh option to both this method and the async one to force it to eagerly get the latest value, perhaps useful during development..
            # TODO: What's a good way to force the request to happen now and block until it's done?
            #   The following should work thanks to the refresh_lock and the early exiting, but it feels like there's got to be a cleaner way to do all this?
            self.refresh()

        if self._config is None:
            return ResolvedVariable(name=variable_name, value=None, _reason='missing_config')

        return self._config.resolve_serialized_value(variable_name, targeting_key, attributes)

    def shutdown(self):
        """Stop the background polling thread and clean up resources."""
        if self._shutdown:
            return
        self._shutdown = True
        self._worker_awaken.set()

        # Join the thread so that resources get cleaned up in tests
        # It might be reasonable to modify this so this _only_ happens in tests, but for now it seems fine.
        self._worker_thread.join(timeout=5)
