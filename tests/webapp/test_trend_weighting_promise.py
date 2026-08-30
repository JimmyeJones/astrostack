"""The trend cards may only promise "counted less" when a stack really did it.

"Focus & sharpness" and "Clouds & haze" both reassured the reader that the
night's soft / hazy subs "were automatically counted less in your stack". They
are *capture-night* cards and knew nothing about any run, so the sentence was
unconditional: an interactive stack with quality weighting unticked, and a
target that had never been stacked at all, got the same confident promise. The
hands-off chains do enable weighting, so on the walk-away path the claim usually
held — which is exactly what makes the wrong cases invisible.

Both endpoints now carry ``weighting``, read from the newest genuine stack's own
provenance header, and the copy follows it (see ``weightingClause`` in
``frontend/src/components/focusTrend.ts``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow

_ENDPOINTS = ("focus-trend", "transparency-trend")


def _add_night(data_root: Path, safe: str) -> None:
    """One session of accepted subs measured on *both* axes, so a single night
    feeds both cards and neither self-hides."""
    base = datetime(2026, 7, 10, 22, 0, 0)
    fwhms = [3.0, 3.1, 3.0, 3.2, 4.4, 4.6, 4.8, 5.0, 5.1]
    scores = [1000, 1020, 980, 990, 700, 520, 480, 450, 420]
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for i, (fw, sc) in enumerate(zip(fwhms, scores, strict=True)):
                proj.add_frame(FrameRow(
                    source_path=f"/synthetic/weighting/{safe}-{i}.fit",
                    timestamp_utc=(base + timedelta(minutes=3 * i)).isoformat(),
                    exposure_s=10.0,
                    accept=True,
                    fwhm_px=fw,
                    transparency_score=sc,
                ))
        finally:
            proj.close()
    finally:
        lib.close()


def _add_run(data_root: Path, safe: str, *, options: dict,
             weighted: bool | None, name: str = "master") -> int:
    """Register a stack run. ``weighted`` stamps the engine's own ``WGTMODE``
    provenance card (True), leaves it off (False), or writes no FITS at all
    (None — the "can't tell" case)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        fits_path: Path | None = None
        if weighted is not None:
            fits_path = tdir / f"{name}.fits"
            hdr = fits.Header()
            if weighted:
                hdr["WGTMODE"] = ("quality", "per-frame weighting mode")
                hdr["WGTNDOWN"] = (4, "frames down-weighted")
            fits.PrimaryHDU(data=np.ones((3, 8, 8), np.float32),
                            header=hdr).writeto(fits_path, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-07-11T02:00:00Z",
                output_basename=name,
                fits_path=str(fits_path) if fits_path else None,
                tiff_path=None, preview_path=None, n_frames_used=9,
                canvas_h=8, canvas_w=8, coverage_min=1, coverage_max=9,
                options_json=json.dumps(options),
            ))
        finally:
            proj.close()
        return int(run_id)
    finally:
        lib.close()


def _weighting(client, safe: str, endpoint: str) -> str | None:
    body = client.get(f"/api/targets/{safe}/{endpoint}").json()
    assert body is not None, f"{endpoint} self-hid — the fixture has too little data"
    return body.get("weighting")


def test_a_target_that_was_never_stacked_promises_nothing(
        client, solved_library, data_root):
    """The worst case the old copy covered up: no run has counted anything, and
    the card still said the subs "were counted less in your stack"."""
    _add_night(data_root, "M_42")
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "unstacked"


def test_a_stack_that_really_weighted_earns_the_promise(
        client, solved_library, data_root):
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42", options={"quality_weighted": True}, weighted=True)
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "applied"


def test_a_stack_that_did_not_weight_is_reported_honestly(
        client, solved_library, data_root):
    """Weighting off — and, identically for the reader, weighting *requested* but
    ignored by an order-statistic min/max combine (which stamps WGTSKIP, not
    WGTMODE). Both are "your subs counted the same", so both read the same."""
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42", options={"quality_weighted": False}, weighted=False)
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "not_applied"


def test_the_options_flag_alone_does_not_earn_the_promise(
        client, solved_library, data_root):
    """The claim is about what the *combine* did, not what was asked for: a run
    whose options say ``quality_weighted`` but whose master carries no WGTMODE
    (min/max ignores weights entirely) must not say the subs counted less."""
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42",
             options={"quality_weighted": True, "min_max_reject": True},
             weighted=False)
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "not_applied"


def test_an_editor_export_is_not_the_stack_that_counted_anything(
        client, solved_library, data_root):
    """Editor-export and channel-combine rows live in ``stack_runs`` too but
    carry no stack knobs — the card must look past them to a genuine run, the
    same way reprocess does."""
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42", options={"quality_weighted": True}, weighted=True,
             name="real")
    _add_run(data_root, "M_42", options={"editor_recipe": {"ops": []}},
             weighted=False, name="export")
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "applied"


def test_an_unreadable_master_says_it_cannot_tell(
        client, solved_library, data_root):
    """No FITS to read ⇒ no claim either way; the copy falls back to the general
    wording rather than inventing a verdict."""
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42", options={"quality_weighted": True}, weighted=None)
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "unknown"


def test_the_newest_genuine_stack_is_the_one_that_answers(
        client, solved_library, data_root):
    """A target restacked without weighting is no longer entitled to the promise
    an older, weighted run earned."""
    _add_night(data_root, "M_42")
    _add_run(data_root, "M_42", options={"quality_weighted": True}, weighted=True,
             name="old")
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target("M_42")))
        newer = tdir / "newer.fits"
        fits.PrimaryHDU(data=np.ones((3, 8, 8), np.float32)).writeto(
            newer, overwrite=True)
        proj = lib.open_target("M_42")
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-07-12T02:00:00Z",
                output_basename="newer", fits_path=str(newer), tiff_path=None,
                preview_path=None, n_frames_used=9, canvas_h=8, canvas_w=8,
                coverage_min=1, coverage_max=9,
                options_json=json.dumps({"quality_weighted": False}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()
    for endpoint in _ENDPOINTS:
        assert _weighting(client, "M_42", endpoint) == "not_applied"
