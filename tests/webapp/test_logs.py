"""In-app log buffer endpoint."""

from __future__ import annotations

import logging


def test_logs_endpoint_captures_recent_messages(client):
    logging.getLogger("seestack.stack.test").warning(
        "Output canvas: 11194x14127 union of 2773 footprints",
    )
    r = client.get("/api/logs", params={"level": "WARNING"})
    assert r.status_code == 200
    body = r.json()
    msgs = [e["message"] for e in body["logs"]]
    assert any("11194x14127" in m for m in msgs)
    assert body["last_seq"] >= 1


def test_logs_level_filter_excludes_info(client):
    logging.getLogger("seestack.test").info("an info line that should be filtered out")
    logging.getLogger("seestack.test").error("a distinctive error line xyzzy")
    r = client.get("/api/logs", params={"level": "ERROR"})
    msgs = [e["message"] for e in r.json()["logs"]]
    assert any("xyzzy" in m for m in msgs)
    assert all("should be filtered out" not in m for m in msgs)


def test_a_failure_with_a_traceback_reaches_the_log(client):
    """The records the Logs page exists for were the ones it never showed.

    ``RingBufferLogHandler.emit`` formatted a record's traceback with
    ``self.formatException`` — a :class:`logging.Formatter` method, not a
    :class:`logging.Handler` one — so **every** record carrying ``exc_info``
    raised ``AttributeError`` before it could be appended, was swallowed by the
    handler's own "logging must never raise" guard, and vanished. So every
    ``log.exception`` in the app (a failed job, a crashed stack — exactly what a
    walk-away box is asked about afterwards, and what the read-only observer GETs
    ``/api/logs`` to find) was missing from the Logs page, which then read as an
    install with no errors at all.
    """
    try:
        raise ValueError("No accepted frames are plate-solved yet")
    except ValueError:
        logging.getLogger("webapp.jobs").exception("job deadbeef (stack) failed")

    r = client.get("/api/logs", params={"level": "ERROR"})
    assert r.status_code == 200
    msgs = [e["message"] for e in r.json()["logs"]]
    hit = next((m for m in msgs if "job deadbeef (stack) failed" in m), None)
    assert hit is not None, "the record itself never reached the buffer"
    # And the traceback came with it — the reason the record is worth keeping.
    assert "Traceback (most recent call last)" in hit
    assert "No accepted frames are plate-solved yet" in hit
