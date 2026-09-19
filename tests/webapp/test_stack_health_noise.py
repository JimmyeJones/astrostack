"""The √N yardstick where the person who needs it will actually see it.

"Your stack came in well under what its subs should give" is the single most
useful early warning a beginner never gets — and until now it rendered only on
the "One frame vs your stack" card, behind a *See the difference* button on the
History page. This pins it on the "How's my stack?" panel the Target page shows
unprompted, and pins the three things that make that affordable and honest:

* the health endpoint reads the measurement the reveal card **already stamped**
  and never measures one itself (a Target-page view must not reload a master and
  re-debayer a sub);
* a stamp whose master has since been re-stacked is a **miss**, not a stale claim
  about a picture that no longer exists;
* the card and the note read **one** verdict, so they can never describe the same
  stack differently.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _write_master(path: Path, sigma: float, seed: int = 0) -> None:
    """A 3-channel linear master. A *quiet* one (small sigma) reads as a healthy
    deep stack against the fixture's raw subs; a noisy one reads as a stack that
    got nowhere near what its frames should have bought."""
    import numpy as np
    from astropy.io import fits

    rng = np.random.default_rng(seed)
    cube = rng.normal(0.0, sigma, size=(3, 320, 480)).astype(np.float32)
    fits.PrimaryHDU(cube).writeto(path, overwrite=True)


def _register(data_root, safe: str, master: Path, *, n_frames: int = 42,
              is_mosaic: bool = False) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        preview = master.with_suffix(".png")
        Image.new("RGB", (4, 4), (10, 20, 30)).save(preview)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(master), tiff_path=None,
                preview_path=str(preview), n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=n_frames,
                coverage_max=n_frames, coverage_thin_frac=0.0,
                options_json=json.dumps({"sigma_clip": True}),
                calstat="dark+flat", total_exposure_s=1260.0,
                is_mosaic=is_mosaic,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _master_path(solved_library, safe: str, name: str) -> Path:
    lib = Library.open_or_create(solved_library / "library")
    try:
        return Path(lib.target_dir(lib.find_target(safe))) / name
    finally:
        lib.close()


def _count_measurements(monkeypatch) -> list[int]:
    from webapp.routers import stack as stack_router

    real = stack_router._measure_noise_ratio
    calls: list[int] = []

    def counted(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(stack_router, "_measure_noise_ratio", counted)
    return calls


def _kinds(client, safe: str, run_id: int) -> list[str]:
    body = client.get(f"/api/targets/{safe}/stack-health?run_id={run_id}").json()
    return [n["kind"] for n in body["notes"]]


def _measure(client, safe: str, run_id: int) -> dict:
    """Hit the reveal card's endpoint once — which is what leaves the stamp the
    health note reads."""
    return client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()


def test_an_underperforming_stack_says_so_on_the_health_card(
        client, solved_library):
    """A master barely quieter than a single raw sub is a 42-frame stack that
    bought almost nothing — the case the nudge exists for."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_noisy.fits")
    _write_master(master, sigma=50.0)          # ≈ a raw sub's own grain
    run_id = _register(solved_library, safe, master)

    measured = _measure(client, safe, run_id)
    assert measured["ratio"] is not None
    assert measured["expected_verdict"] == "low"

    body = client.get(f"/api/targets/{safe}/stack-health?run_id={run_id}").json()
    note = next(n for n in body["notes"] if n["kind"] == "noise_low")
    assert "42 subs should cut the background noise about 6.5×" in note["message"]
    assert "usually means" in note["message"]     # suggests, never asserts
    assert note["severity"] == "info"
    assert note["action"] is None


def test_a_healthy_stack_is_not_nudged(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_quiet.fits")
    _write_master(master, sigma=2.0)           # a genuinely deep stack
    run_id = _register(solved_library, safe, master)

    assert _measure(client, safe, run_id)["expected_verdict"] == "expected"
    assert "noise_low" not in _kinds(client, safe, run_id)


def test_the_health_card_never_measures_the_noise_itself(
        client, solved_library, monkeypatch):
    """The whole reason this is cheap: the note reads a stamp or says nothing. A
    Target-page view that reloaded the master and re-debayered a sub would be a
    real regression on a page that must stay cheap."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_unmeasured.fits")
    _write_master(master, sigma=50.0)
    run_id = _register(solved_library, safe, master)
    calls = _count_measurements(monkeypatch)

    # Nothing has ever revealed this run, so there is no stamp to read.
    assert "noise_low" not in _kinds(client, safe, run_id)
    assert calls == []

    # …and it self-heals the moment the reveal measures it once.
    _measure(client, safe, run_id)
    assert len(calls) == 1
    assert "noise_low" in _kinds(client, safe, run_id)
    assert len(calls) == 1, "reading the note must not re-measure either"


def test_a_stamp_from_a_replaced_master_is_never_served_as_the_verdict(
        client, solved_library, monkeypatch):
    """A re-stack writes a new master at the same path. The old number describes
    a picture that no longer exists, so the fingerprint must reject it rather
    than let the card accuse the new stack of the old one's shortfall."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_restacked.fits")
    _write_master(master, sigma=50.0)
    run_id = _register(solved_library, safe, master)
    _measure(client, safe, run_id)
    assert "noise_low" in _kinds(client, safe, run_id)

    # Re-stacked in place: a different (much quieter) master at the same path.
    _write_master(master, sigma=2.0, seed=1)
    calls = _count_measurements(monkeypatch)
    assert "noise_low" not in _kinds(client, safe, run_id)
    assert calls == [], "a fingerprint miss must stay silent, not measure"


def test_a_small_stack_is_never_judged_by_the_yardstick(client, solved_library):
    """Below ten frames a single unlucky reference sub swings the ratio more than
    the physics does, so both surfaces say nothing at all."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_small.fits")
    _write_master(master, sigma=50.0)
    run_id = _register(solved_library, safe, master, n_frames=6)

    assert _measure(client, safe, run_id)["expected_verdict"] is None
    assert "noise_low" not in _kinds(client, safe, run_id)


def test_a_mosaic_gets_no_verdict_on_either_surface(client, solved_library):
    """The owner shoots mosaics. The ratio is measured over a central crop, whose
    depth is a *panel's* subs, while `n_frames_used` counts the whole target's —
    so a perfectly healthy mosaic reads "low" at every depth. Both the card and
    the note therefore say nothing at all rather than something wrong."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master_mosaic.fits")
    _write_master(master, sigma=50.0)          # would read "low" as a single field
    run_id = _register(solved_library, safe, master, is_mosaic=True)

    measured = _measure(client, safe, run_id)
    assert measured["ratio"] is not None, "the number itself is still measured"
    assert measured["expected_verdict"] is None
    assert "noise_low" not in _kinds(client, safe, run_id)


# --- "at the same settings as your subs" is a claim about a set -------------
#
# The "How to add darks" guide pre-fills the numbers off `recommended_dark_spec`,
# which takes the *median* exposure of the accepted subs. A target is one folder,
# never one exposure, so a Seestar owner who shoots 10 s on a bright night and
# 30 s on a faint one gets told to go and shoot a night of darks at 20 s — a
# length none of their frames was shot at, offered under the words "the same
# settings as your subs".


def _split_exposures(data_root, safe: str, short_s: float, long_s: float) -> int:
    """Rewrite the target's accepted subs into two equal nights — half at
    ``short_s``, half at ``long_s`` — so a fixture target can be the ordinary
    two-nights-two-lengths shape a Seestar owner ends up with. Returns how many
    frames were rewritten."""
    import sqlite3

    lib = Library.open_or_create(data_root / "library")
    try:
        db = lib.target_dir(lib.find_target(safe)) / "project.sqlite"
    finally:
        lib.close()
    con = sqlite3.connect(db)
    try:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM frames WHERE accept=1 ORDER BY id").fetchall()]
        assert len(ids) >= 2, "two nights need two frames"
        # The majority gets the short length, so the median is one of the two
        # real lengths rather than something between them — which is the case
        # this fixture can carry. (An even split, where the median is a length
        # nobody shot, is pinned at engine level.)
        half = (len(ids) + 1) // 2
        for fid in ids[:half]:
            con.execute("UPDATE frames SET exposure_s=? WHERE id=?", (short_s, fid))
        for fid in ids[half:]:
            con.execute("UPDATE frames SET exposure_s=? WHERE id=?", (long_s, fid))
        con.commit()
        return len(ids)
    finally:
        con.close()


def test_the_darks_guide_names_every_length_the_target_was_shot_at(
        client, solved_library):
    """The set travels beside the median on the wire, so the guide can stop
    describing a target by one length when it holds two. (The sharpest case —
    an *even* split, where the median is a length nobody shot at all — is pinned
    in ``tests/test_stackhealth.py``; this fixture has three accepted subs.)"""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master.fits")
    _write_master(master, sigma=2.0)
    run_id = _register(solved_library, safe, master)
    _split_exposures(solved_library, safe, 10.0, 30.0)

    spec = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()["dark_spec"]

    assert spec["exposure_s"] == 10.0, "the median every existing reader gates on"
    assert spec["exposures_s"] == [10.0, 30.0], (
        "the 30 s subs are invisible behind the median, and need their own dark")


def test_an_ordinary_single_length_target_reports_one_length_on_the_wire(
        client, solved_library):
    """Every library that has never changed sub length is untouched."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master.fits")
    _write_master(master, sigma=2.0)
    run_id = _register(solved_library, safe, master)

    spec = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()["dark_spec"]

    assert spec["exposures_s"] == [spec["exposure_s"]]


# --- …and the same claim about the other setting the guide prints -----------


def _split_gains(data_root, safe: str, low: float, high: float) -> int:
    """The gain twin of ``_split_exposures`` — half the accepted subs at *low*,
    half at *high*, the shape an owner ends up with after changing the setting
    between nights."""
    import sqlite3

    lib = Library.open_or_create(data_root / "library")
    try:
        db = lib.target_dir(lib.find_target(safe)) / "project.sqlite"
    finally:
        lib.close()
    con = sqlite3.connect(db)
    try:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM frames WHERE accept=1 ORDER BY id")]
        half = (len(ids) + 1) // 2
        for fid in ids[:half]:
            con.execute("UPDATE frames SET gain=? WHERE id=?", (low, fid))
        for fid in ids[half:]:
            con.execute("UPDATE frames SET gain=? WHERE id=?", (high, fid))
        con.commit()
        return len(ids)
    finally:
        con.close()


def test_the_darks_guide_names_every_gain_the_target_was_shot_at(
        client, solved_library):
    """The gain half of the same sentence, which until now took a median of a
    *discrete setting*: shoot half a target at gain 80 and half at 200 and the
    guide asked for darks at a gain the camera cannot be dialled to."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master.fits")
    _write_master(master, sigma=2.0)
    run_id = _register(solved_library, safe, master)
    _split_gains(solved_library, safe, 80.0, 200.0)

    spec = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()["dark_spec"]

    assert spec["gains"] == [80.0, 200.0], (
        "the gain-200 subs are invisible behind the representative, and need "
        "their own darks — nothing anywhere rescales a gain")
    # Whatever single value stands for the target, it has to be one the camera
    # really was set to — the invariant a median cannot keep.
    assert spec["gain"] in spec["gains"]


def test_an_ordinary_single_gain_target_reports_one_gain_on_the_wire(
        client, solved_library):
    """Every library shot at one gain — which is every Seestar library until
    someone changes the setting — is untouched."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "master.fits")
    _write_master(master, sigma=2.0)
    run_id = _register(solved_library, safe, master)

    spec = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()["dark_spec"]

    assert spec["gains"] == [spec["gain"]]
