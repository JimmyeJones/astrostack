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


def _register(data_root, safe: str, master: Path, *, n_frames: int = 42) -> int:
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
