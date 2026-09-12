"""Tests for the request monitor that counts HTTP traffic and failures."""

from unittest.mock import patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from custom_components.iqtec.monitor import PollRecord, RequestMonitor

URL = "http://iqtec.home/control/?1/3/"


def _response(body: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = URL
    response._content = body
    return response


def _session() -> tuple[RequestMonitor, requests.Session]:
    monitor = RequestMonitor()
    session = requests.Session()
    monitor.install(session)
    return monitor, session


def test_requests_and_bytes_are_charged_to_the_running_poll():
    monitor, session = _session()
    record = PollRecord()

    with patch.object(HTTPAdapter, "send", return_value=_response(b"1/3/0=Obyvak\n")):
        monitor.run(record, session.get, URL)
        # Outside a poll, such as a command, only the totals move.
        session.get(URL)

    assert record.requests == 1
    assert record.bytes_received == 13
    assert record.errors == 0
    assert record.duration >= 0
    assert monitor.stats.requests == 2
    assert monitor.stats.bytes_received == 26
    assert monitor.stats.errors == 0


def test_timeouts_are_counted_and_still_raised():
    monitor, session = _session()
    record = PollRecord()

    with (
        patch.object(HTTPAdapter, "send", side_effect=requests.exceptions.ReadTimeout("slow")),
        pytest.raises(requests.exceptions.ReadTimeout),
    ):
        monitor.run(record, session.get, URL)

    assert record.requests == 1
    assert record.errors == 1
    assert monitor.stats.errors == 1
    assert monitor.stats.timeouts == 1
    assert monitor.stats.connection_errors == 0


@pytest.mark.parametrize(
    ("error", "timeouts", "connection_errors"),
    [
        (requests.exceptions.ConnectTimeout("no route"), 1, 0),
        (requests.exceptions.ConnectionError("refused"), 0, 1),
        (requests.exceptions.ChunkedEncodingError("cut off"), 0, 0),
    ],
)
def test_errors_are_sorted_into_timeouts_and_connection_errors(error, timeouts, connection_errors):
    monitor, session = _session()

    with patch.object(HTTPAdapter, "send", side_effect=error), pytest.raises(type(error)):
        session.get(URL)

    assert monitor.stats.errors == 1
    assert monitor.stats.timeouts == timeouts
    assert monitor.stats.connection_errors == connection_errors


def test_poll_bookkeeping_tracks_runs_of_failures():
    monitor = RequestMonitor()
    stats = monitor.stats

    monitor.poll_finished(None)
    assert (stats.polls, stats.failed_polls, stats.consecutive_failures) == (1, 0, 0)
    assert stats.last_success_at is not None
    assert stats.last_error is None

    monitor.poll_finished(ValueError("boom"))
    monitor.poll_finished(ValueError("again"))
    assert (stats.polls, stats.failed_polls, stats.consecutive_failures) == (3, 2, 2)
    assert stats.last_error == "ValueError: again"
    assert stats.last_error_at is not None

    monitor.poll_finished(None)
    assert (stats.polls, stats.failed_polls, stats.consecutive_failures) == (4, 2, 0)
    # The last error stays visible after recovery.
    assert stats.last_error == "ValueError: again"


def test_stats_serialise_for_diagnostics():
    monitor = RequestMonitor()
    monitor.poll_finished(RuntimeError("x"))
    monitor.stats.last_poll = PollRecord(requests=3, bytes_received=1200, duration=0.4321)

    as_dict = monitor.stats.as_dict()

    assert as_dict["failed_polls"] == 1
    assert as_dict["last_error"] == "RuntimeError: x"
    assert isinstance(as_dict["last_error_at"], str)
    assert as_dict["last_success_at"] is None
    assert as_dict["last_poll"] == {"requests": 3, "bytes_received": 1200, "errors": 0, "duration": 0.432}
