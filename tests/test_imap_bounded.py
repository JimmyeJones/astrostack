"""_imap_bounded: bounded in-flight work so results can't pile up and OOM."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from seestack.stack.stacker import _imap_bounded


def test_processes_every_item_once():
    items = list(range(100))
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [(item, fut.result()) for item, fut in _imap_bounded(ex, lambda x: x * x, items, 8)]
    assert sorted(i for i, _ in out) == items
    assert all(r == i * i for i, r in out)


def test_never_exceeds_max_in_flight():
    max_in_flight = 5
    current = 0
    peak = 0
    lock = threading.Lock()

    def fn(x):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        time.sleep(0.003)
        with lock:
            current -= 1
        return x

    with ThreadPoolExecutor(max_workers=16) as ex:  # more workers than the cap
        out = [item for item, _ in _imap_bounded(ex, fn, range(300), max_in_flight)]

    assert sorted(out) == list(range(300))
    # Concurrency is capped by max_in_flight, not the executor's worker count.
    assert peak <= max_in_flight
