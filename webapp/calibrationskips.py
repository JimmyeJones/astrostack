"""Which folders under ``incoming/`` the scan passed over as calibration data.

``GET /api/incoming-lag`` asks *"are there subs on disk that my library has no
row for?"* and offers a **Scan incoming** button over the answer. A folder of
declared darks is in that state for ever — the scan passes it over on purpose
(:func:`seestack.io.scanner._calibration_units`, v0.455.0) — so naming it would
be a promise no scan can keep, which is the one thing that note must never do.

It has therefore always excluded the folders the Calibration page's build offer
lists (:func:`seestack.calibrate.discover.find_calibration_folders`), and
v0.455.0 claimed the two sets were *identical*: the scanner's skip carries
``discover.MIN_FRAMES``, so "a folder could not fall between them". **That claim
was only ever true when the calibration frames sit directly in a top-level
folder** (observer issue #1088). The two sides name folders at different
granularity and under different floors:

* the scan plans a **recursive unit** whose folder is the top-level directory,
  so darks in ``Darks/20s/`` are the unit ``Darks``, while discovery classifies
  an **individual directory** and names it ``Darks/20s`` — and the Calibration
  page's own ``discover.MAX_DEPTH = 2`` deliberately invites that nesting;
* ``MIN_FRAMES`` is the scan's floor on the whole **unit** and discovery's floor
  on each **directory**, so ``Darks 20s/{a,b}`` holding three frames each is one
  skipped six-frame unit that discovery does not offer at all.

Either way the note named a folder over a button that could not import it.

**Why it is remembered rather than derived.** The verdict comes from the frames'
own ``IMAGETYP`` cards, and the lag note's whole design is that nothing it does
walks, opens or ``stat``s anything under ``incoming/`` (AGENTS.md §10) — it is
handed the watcher's existing listing. The scan has just read those headers, with
the real unit boundaries in hand, so the scan writes down what it skipped: one
JSON value in the registry's existing ``library_meta`` key/value table, exactly
as :mod:`webapp.unreadablesubs` and :mod:`webapp.skipped_folders` remember their
own findings. No schema change, and a build that predates the key simply never
asks for it.

**Why matching stays exact.** The record is keyed by
:attr:`seestack.io.scanner.PlannedUnit.folder` — the *unit* the scan actually
passed over — so the reader compares it to a planned unit's folder with plain
equality and needs no prefix roll-up. That matters: a roll-up would also silence
genuine lag on a **light** unit holding a nested dark folder
(``M 42_sub/darks/``), which the scan ingests, and it could not reach the split
``Darks 20s/{a,b}`` case at all.

**Why it cannot go stale into a lie.** Every whole-library scan re-reads every
unit, so its answer is complete and simply replaces the last: a folder the owner
drops lights into is ingested on the next scan and leaves the record then, and
the note goes back to speaking about it. In the window before that scan the note
stays quiet about the folder — and it would anyway, because
:data:`webapp.incominglag.LAG_MIN_AGE_S` gives a folder two hours of silence
after its newest file stops moving, which is many watcher polls. A *scoped* scan
("bring this one folder in") sees only its own folder and therefore never
rewrites the whole record.

Read-only throughout: nothing here scans, ingests, or writes to ``incoming/``.
"""

from __future__ import annotations

import json

#: Key in the registry's ``library_meta`` table. Additive by construction — the
#: table already exists, so remembering this needs no schema bump.
SKIPPED_CALIBRATION_META_KEY = "scan_skipped_calibration_folders"

#: Never remember more than this many folders. The realistic count is the one or
#: two the Calibration page asked the owner to create; a drop folder holding
#: dozens of declared-calibration units is not a shape any note can express. The
#: cap drops the folders sorted last, and dropping one makes the lag note *speak*
#: about it rather than go quiet — the same direction the bug this record fixes
#: already errs in, and the safe one for a record whose whole job is silencing.
MAX_REMEMBERED_FOLDERS = 64


def folders_from_scan(scan) -> list[str]:  # noqa: ANN001
    """The unit folders one scan passed over as calibration data.

    ``scan`` is a :class:`seestack.io.scanner.ScanResult`. A record whose folder
    the scan did not note (``None`` — an older engine, or a unit whose folder
    could not be derived) is dropped rather than guessed at: ``""`` is a real
    answer here (frames loose in the drop folder itself), so there is no spare
    value to mean "unknown".
    """
    out: list[str] = []
    for skip in getattr(scan, "skipped_calibration_folders", []):
        folder = getattr(skip, "folder", None)
        if isinstance(folder, str):
            out.append(folder)
    return out


def encode_calibration_skips(folders: list[str]) -> str:
    """The remembered form: ``{"folders": [folder, …]}``, sorted and capped.

    Sorted so the value is byte-stable between two scans that found the same
    thing — a record that churned would rewrite the registry on every poll-driven
    scan for no reason.
    """
    kept = sorted(set(folders))
    return json.dumps({"folders": kept[:MAX_REMEMBERED_FOLDERS]})


def decode_calibration_skips(raw: str | None) -> set[str]:
    """Read back :func:`encode_calibration_skips`, tolerating anything else.

    Read on a poll, so a truncated write, a hand-edited registry or a shape from
    some future version must degrade to "nothing known" — which is the behaviour
    before this record existed — rather than 500 the Dashboard.
    """
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return set()
    if not isinstance(parsed, dict):
        return set()
    rows = parsed.get("folders")
    if not isinstance(rows, list):
        return set()
    return {row for row in rows if isinstance(row, str)}


def remember_calibration_skips(lib, folders: list[str]) -> None:  # noqa: ANN001
    """Write one whole-library scan's answer down, replacing the last.

    Replacing rather than merging is the point: the scan looked at every unit, so
    its answer is complete, and a folder that has stopped being calibration data
    must be able to leave the record.
    """
    lib.set_meta(SKIPPED_CALIBRATION_META_KEY, encode_calibration_skips(folders))


def recall_calibration_skips(lib) -> set[str]:  # noqa: ANN001
    """The unit folders the last whole-library scan passed over as calibration."""
    return decode_calibration_skips(lib.get_meta(SKIPPED_CALIBRATION_META_KEY))
