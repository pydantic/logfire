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
from requests import Response, Session

from logfire._internal.client import UA_HEADER
from logfire._internal.utils import UnexpectedResponse
from logfire.variables.abstract import VariableProvider, VariableResolutionDetails
from logfire.variables.config import VariablesConfig

__all__ = ('LogfireRemoteVariableProvider',)


# TODO: Do we need to provide a mechanism for whether the LogfireRemoteProvider should block to retrieve the config
#   during startup or do synchronize in the background?
class LogfireRemoteVariableProvider(VariableProvider):
    """Variable provider that fetches configuration from a remote Logfire API.

    The threading implementation draws heavily from opentelemetry.sdk._shared_internal.BatchProcessor.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        block_before_first_fetch: bool,
        polling_interval: timedelta | float = timedelta(seconds=30),
    ):
        """Create a new remote variable provider.

        Args:
            base_url: The base URL of the Logfire API.
            token: Authentication token for the Logfire API.
            block_before_first_fetch: Whether to block on first variable access until configuration
                is fetched from the remote API.
            polling_interval: How often to poll for configuration updates. Can be a timedelta or
                a number of seconds.
        """
        super().__init__()

        self._base_url = base_url
        self._session = Session()
        self._session.headers.update({'Authorization': token, 'User-Agent': UA_HEADER})
        self._block_before_first_fetch = block_before_first_fetch
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
            self._worker_awaken.wait(self._polling_interval.total_seconds())
            if self._shutdown:
                break
            # TODO: Ideally we'd be able to terminate while the following request was going even if it takes a while
            #   Note it's far more reasonable to terminate this worker thread "gracelessly" than an OTel exporter's.
            #   Is there anything similar to an anyio CancelScope we can use here?
            self.refresh()
            self._worker_awaken.clear()

    def _get_raw(self, endpoint: str, params: dict[str, Any] | None = None) -> Response:
        # TODO: Should we try to unify this and `_get` with LogfireClient in some way? Are they even necessary?
        response = self._session.get(urljoin(self._base_url, endpoint), params=params)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _get(self, endpoint: str, *, params: dict[str, Any] | None = None, error_message: str) -> Any:
        try:
            return self._get_raw(endpoint, params).json()
        except UnexpectedResponse:
            # TODO: Update the following logic to be smarter
            # TODO: Handle any error here, not just UnexpectedResponse, so we don't crash user application on failure
            warnings.warn(error_message, category=RuntimeWarning)

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

            variables_config_data = self._get('/v1/variables/', error_message='Error retrieving variables')
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
    ) -> VariableResolutionDetails[str | None]:
        """Resolve a variable's serialized value from the remote configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails containing the serialized value (or None if not found).
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
            return VariableResolutionDetails(value=None, _reason='missing_config')

        # TODO: Move the following down to a method on VariablesConfig
        variable_config = self._config.variables.get(variable_name)
        if variable_config is None:
            return VariableResolutionDetails(value=None, _reason='unrecognized_variable')

        variant = variable_config.resolve_variant(targeting_key, attributes)
        if variant is None:
            return VariableResolutionDetails(value=None, _reason='resolved')
        else:
            return VariableResolutionDetails(value=variant.serialized_value, variant=variant.key, _reason='resolved')

    def shutdown(self):
        """Stop the background polling thread and clean up resources."""
        if self._shutdown:
            return
        self._shutdown = True
        self._worker_awaken.set()

        # TODO: Is there any circumstance under which we _should_ join the thread here?
        # self._worker_thread.join(None)
