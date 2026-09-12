"""Counts the HTTP traffic the integration causes and the failures it meets.

The controller is an embedded device with a small HTTP server, so the number of
requests it has to answer matters. piqtec talks to it through a ``requests``
session; mounting a counting transport adapter on that session sees every
request, every reply and every timeout without touching the library itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter


@dataclass
class PollRecord:
    """What one read of the controller cost."""

    requests: int = 0
    bytes_received: int = 0
    errors: int = 0
    duration: float = 0.0


@dataclass
class RequestStats:
    """Everything counted since the integration was loaded."""

    requests: int = 0
    bytes_received: int = 0
    errors: int = 0
    timeouts: int = 0
    connection_errors: int = 0

    polls: int = 0
    failed_polls: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    last_error_at: datetime | None = None
    last_success_at: datetime | None = None

    last_poll: PollRecord = field(default_factory=PollRecord)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly copy for diagnostics."""
        return {
            "requests": self.requests,
            "bytes_received": self.bytes_received,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "connection_errors": self.connection_errors,
            "polls": self.polls,
            "failed_polls": self.failed_polls,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_poll": {
                "requests": self.last_poll.requests,
                "bytes_received": self.last_poll.bytes_received,
                "errors": self.last_poll.errors,
                "duration": round(self.last_poll.duration, 3),
            },
        }


class RequestMonitor:
    """Attributes HTTP requests to the poll that caused them.

    ``run`` executes a blocking piqtec call in the current (executor) thread and
    notes the poll in thread-local storage, so the adapter can charge requests
    made from that thread to the right ``PollRecord``. Requests made outside a
    poll, such as commands, only reach the running totals.
    """

    def __init__(self) -> None:
        """Start with empty counters."""
        self.stats = RequestStats()
        self._local = threading.local()

    def install(self, session: requests.Session) -> None:
        """Route the session's traffic through a counting adapter."""
        for prefix in ("http://", "https://"):
            session.mount(prefix, _CountingAdapter(self))

    def run[T](self, record: PollRecord, func: Callable[..., T], *args: Any) -> T:
        """Call ``func`` and charge its requests and duration to ``record``."""
        self._local.record = record
        started = time.monotonic()
        try:
            return func(*args)
        finally:
            record.duration = time.monotonic() - started
            self._local.record = None

    def poll_finished(self, error: BaseException | None) -> None:
        """Book a completed poll; ``error`` is what made it fail, if anything."""
        stats = self.stats
        stats.polls += 1
        if error is None:
            stats.consecutive_failures = 0
            stats.last_success_at = datetime.now(UTC)
            return
        stats.failed_polls += 1
        stats.consecutive_failures += 1
        stats.last_error = f"{type(error).__name__}: {error}"
        stats.last_error_at = datetime.now(UTC)

    def _note_request(self, nbytes: int, error: BaseException | None) -> None:
        stats = self.stats
        record: PollRecord | None = getattr(self._local, "record", None)
        stats.requests += 1
        if record is not None:
            record.requests += 1
        if error is None:
            stats.bytes_received += nbytes
            if record is not None:
                record.bytes_received += nbytes
            return
        stats.errors += 1
        if record is not None:
            record.errors += 1
        # ConnectTimeout is both, and a timeout is the more useful label.
        if isinstance(error, requests.exceptions.Timeout):
            stats.timeouts += 1
        elif isinstance(error, requests.exceptions.ConnectionError):
            stats.connection_errors += 1


class _CountingAdapter(HTTPAdapter):
    """The stock transport, with a tally of what passes through."""

    def __init__(self, monitor: RequestMonitor) -> None:
        super().__init__()
        self._monitor = monitor

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        """Send the request and count it, whether or not it succeeds."""
        try:
            response = super().send(request, **kwargs)
            # Reading the body here means a timeout while receiving it is
            # counted too; piqtec reads the whole reply anyway.
            size = len(response.content)
        except requests.RequestException as err:
            self._monitor._note_request(0, err)
            raise
        self._monitor._note_request(size, None)
        return response
