"""Read-only diagnostics that run on the owner's own library, inside his app.

**Why this exists.** The agents that improve this app work on synthetic data;
the owner's real library — tens of thousands of subs, a hundred targets, every
night he has shot — exists only on his NAS. When a bug needs a measurement only
his data can give (2026-11: is a colour pattern printed on *his* sensor, and
does it depend on temperature?), the only route used to be an agent writing a
script and the owner pasting it into a terminal. He said, rightly, that this is
not his job.

So a question for his library is now **code that ships with the app**: a
:class:`Diagnostic` registered here. After an update the app runs every
diagnostic whose ``(name, version)`` has no stored result, once, as an ordinary
queued job (:mod:`webapp.diagnostics`), and serves the results on
``GET /api/diagnostics`` — a path the observer's read-only token may read. The
observer files each new result as a GitHub issue, and the agents read it there.
Nobody types anything.

**The contract every diagnostic keeps** (the repository is public, AGENTS.md):

* **Read-only.** It may read the library record and open FITS files to read
  them. It never writes, moves or deletes anything — above all nothing under
  ``incoming/`` (AGENTS.md §10).
* **Numbers and catalogue names only.** No file path, no FITS header value
  (the one exception: a short plain equipment word such as a filter name,
  vetted by :func:`seestack.diag.filter_card._token`), no
  site latitude/longitude, no account name, no date finer than a night. The
  result is JSON of counts and measurements; :func:`check_result_is_safe`
  refuses anything that looks like a path or a coordinate pair.
* **Bounded.** It samples (a few hundred subs at most) and checks
  ``should_stop`` between files, so it can be cancelled like any job and never
  holds the single worker for long.
* **Versioned.** Change what it measures → bump ``version``, and it runs again
  after the next update. The old result stays on disk.

Engine code: no ``webapp`` imports.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, NamedTuple

#: ``(phase, done, total)`` — the engine's usual progress shape.
Progress = Callable[[str, int, int], None]
ShouldStop = Callable[[], bool]


@dataclass(frozen=True)
class Diagnostic:
    """One question for the owner's library, answered by ``run``."""
    name: str            # stable slug, e.g. "sensor_pattern_by_temperature"
    version: int         # bump when the measurement changes; it then re-runs
    question: str        # one plain sentence: what this answers, and why
    run: Callable[..., dict[str, Any]]  # (library, *, progress, should_stop) -> JSON-safe dict
    #: Cheap check on the library record alone: is there enough here for the
    #: answer to mean anything? A diagnostic that is not ready is not queued,
    #: and is asked again at the next boot.
    ready: Callable[[Any], bool] | None = None


class DiagnosticStopped(RuntimeError):
    """Raised by a diagnostic when ``should_stop`` asked it to stop."""


class SubRef(NamedTuple):
    """One sub, reduced to what a diagnostic needs to pick it and open it.

    A diagnostic surveys **every** sub of the library before it samples a few
    hundred, and it holds that survey for the whole run. A ``FrameRow`` is
    ``SELECT *`` and carries the sub's plate solution (a FITS header text of
    ~25 cards), so a survey of ``FrameRow`` s cost ~4 kB a sub — on the owner's
    library, tens of thousands of subs, hundreds of MB held for minutes on a
    box with an OOM history. These four columns are all any diagnostic reads.
    The field names match ``FrameRow`` 's, so either can be handed to
    :func:`sub_path`.
    """
    cached_path: str | None
    source_path: str | None
    timestamp_utc: str | None
    sensor_temp_c: float | None


def iter_sub_refs(project: Any, *, accepted_only: bool = False) -> Iterator[SubRef]:
    """``project`` 's subs as :class:`SubRef` s, in ``iter_frames`` ' own order
    (by id) — the same subs, without building a ``FrameRow`` for any of them."""
    for row in project.iter_frame_columns(*SubRef._fields, accepted_only=accepted_only):
        yield SubRef(*row)


def sub_path(f: Any) -> str | None:
    """The sub's readable file — its cache copy if present, else its source —
    by the app's one rule for that (``first_existing_frame_path``)."""
    from seestack.io.project import first_existing_frame_path

    return first_existing_frame_path(getattr(f, "cached_path", None),
                                     getattr(f, "source_path", None))


def registry() -> list[Diagnostic]:
    """Every diagnostic, in the order they run. Import here so a broken one
    fails loudly in the test suite rather than silently at boot."""
    from seestack.diag import filter_card, mosaic_hints, sensor_pattern

    return [sensor_pattern.DIAGNOSTIC, filter_card.DIAGNOSTIC, mosaic_hints.DIAGNOSTIC]


# A host or container path, a Windows path, or two decimals that could be a
# lat/lon pair. Deliberately broad: a false refusal costs one re-worded result;
# a leak cannot be taken back.
_UNSAFE = (
    re.compile(r"(^|[\s\"'(=])(/|~/|[A-Za-z]:\\)[^\s\"']+"),
    re.compile(r"\b(SITELAT|SITELONG|site_lat|site_lon|latitude|longitude)\b", re.I),
)


def check_result_is_safe(result: Any) -> None:
    """Raise ``ValueError`` if any string inside ``result`` looks like a path
    or a location. Numbers are always fine; strings are walked recursively."""
    def walk(v: Any) -> None:
        if isinstance(v, str):
            for pat in _UNSAFE:
                if pat.search(v):
                    raise ValueError(f"diagnostic result contains an unsafe string: {v[:40]!r}")
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(str(k))
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(result)
