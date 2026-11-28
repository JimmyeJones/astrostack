"""Incremental stacking — "Add new subs to the last stack" (``StackOptions.incremental``).

The contract (see :mod:`seestack.stack.incremental`): a full stack is always a
correct answer, and an incremental one is only taken when it is the same stack
plus new subs. So this file pins three things:

* **parity** — a full stack of N subs, then N+M incrementally, against a full
  stack of N+M, for κ-σ and for the weighted mean, with quality weighting on;
* **every fallback** — each reason the saved sums can't be continued produces an
  ordinary full stack, recorded as such;
* **nothing changes when it's off**, and nothing is ever written under
  ``incoming/``.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.io import fits  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import incremental as inc  # noqa: E402
from seestack.stack import stacker as stacker_mod  # noqa: E402
from seestack.stack.accumulator import (  # noqa: E402
    WeightedSumAccumulator,
    WelfordAccumulator,
)
from seestack.stack.photometric import (  # noqa: E402
    compute_photometric_scales,
    photometric_reference,
)
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from seestack.stack.weighting import (  # noqa: E402
    compute_frame_weights,
    weight_yardsticks,
)
from tests.synth import (  # noqa: E402
    make_star_field,
    make_synth_wcs_text,
    write_seestar_fits,
)

FW, FH = 480, 320
WCS = make_synth_wcs_text(width=FW, height=FH)


def _raw(raws: Path, i: int, *, streak: bool = False) -> Path:
    """One sub of the same star field with its own noise. A ``streak`` is a
    two-row satellite trail at a row that depends on ``i``, so trails in
    different subs don't stack on top of each other."""
    path = raws / f"f{i:03d}.fit"
    if not path.exists():
        data = make_star_field(width=FW, height=FH, seed=42, n_stars=30,
                               noise_seed=100 + i)
        if streak:
            y = 40 + (9 * i) % (FH - 80)
            band = data[y:y + 2, 20:FW - 20].astype(np.int64) + 8000
            data[y:y + 2, 20:FW - 20] = np.minimum(band, 65535).astype(np.uint16)
        write_seestar_fits(path, width=FW, height=FH, add_wcs=True, data=data)
    return path


class _Target:
    """A single-field target whose subs share one sky and one plate solution.

    Sub 0 has the lowest FWHM, so it is the reference (every sub points at the
    same centre and ``pick_central_frame`` breaks the tie by FWHM)."""

    def __init__(self, root: Path, raws: Path, name: str = "t") -> None:
        self.raws = raws
        self.raws.mkdir(parents=True, exist_ok=True)
        self.proj = Project.create(root / name, name=name)
        self.ids: dict[int, int] = {}

    def add(self, i: int, *, streak: bool = False, wcs: str = WCS,
            fwhm: float | None = None) -> int:
        path = _raw(self.raws, i, streak=streak)
        fid = self.proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=FW, height_px=FH, bayer_pattern="RGGB",
            wcs_json=wcs, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=fwhm if fwhm is not None else (
                1.8 if i == 0 else 2.0 + 0.15 * (i % 5)),
            star_count=30 - i % 4,
            sky_adu_median=1000.0 + 15.0 * (i % 3),
            transparency_score=1.0 - 0.03 * (i % 5),
            eccentricity_median=0.1 + 0.02 * (i % 4),
            exposure_s=10.0,
        ))
        self.ids[i] = fid
        return fid

    @property
    def sidecar(self) -> Path:
        return self.proj.project_dir / "output" / "master_incremental.npz"

    def run(self, opts: StackOptions):
        return run_stack(self.proj, replace(opts))

    def run_options(self, run_id: int) -> dict:
        run = next(r for r in self.proj.iter_stack_runs() if r.id == run_id)
        return json.loads(run.options_json)

    def close(self) -> None:
        self.proj.close()


def _opts(**kw) -> StackOptions:
    base = dict(incremental=True, quality_weighted=True, max_workers=2)
    base.update(kw)
    return StackOptions(**base)


def _streak(i: int) -> bool:
    return i % 7 == 3


def _pixels(path: Path) -> np.ndarray:
    return np.asarray(fits.getdata(path), dtype=np.float64)


def _parity(full: np.ndarray, incr: np.ndarray) -> tuple[float, float]:
    """(max, 99.9th percentile) of |full − incr| over the image's robust range."""
    assert np.array_equal(np.isfinite(full), np.isfinite(incr)), \
        "NaN (no coverage) must mean the same pixels in both"
    ok = np.isfinite(full)
    lo, hi = np.percentile(full[ok], [0.5, 99.5])
    d = np.abs(full - incr)[ok] / (hi - lo)
    return float(d.max()), float(np.percentile(d, 99.9))


def _run_parity(tmp_path, n: int, m: int, **kw):
    raws = tmp_path / "raws"
    full = _Target(tmp_path, raws, "full")
    part = _Target(tmp_path, raws, "part")
    try:
        for i in range(n + m):
            full.add(i, streak=_streak(i))
        for i in range(n):
            part.add(i, streak=_streak(i))
        r_full = full.run(_opts(**kw))
        r_first = part.run(_opts(**kw))
        assert r_first.incremental_added is None
        assert part.sidecar.is_file()
        for i in range(n, n + m):
            part.add(i, streak=_streak(i))
        r_inc = part.run(_opts(**kw))
        return full, part, r_full, r_inc
    except Exception:
        full.close()
        part.close()
        raise


# ---- parity ------------------------------------------------------------------

def test_kappa_sigma_incremental_matches_a_full_stack(tmp_path, monkeypatch):
    """12 subs, then 6 more added incrementally, against a full stack of 18 —
    with three satellite trails (two in the old subs, one in the new) and
    quality weighting on. Measured: max 4.1e-3, 99.9th percentile 1.9e-3 of the
    robust range; the residue is the old subs keeping the clip decisions they
    had and the new subs being weighted against the frozen yardsticks."""
    aligned: list[int] = []
    real = stacker_mod._align_for_stack

    def spy(frame, *a, **k):  # noqa: ANN001, ANN202
        aligned.append(frame.id)
        return real(frame, *a, **k)

    full, part, r_full, r_inc = _run_parity(tmp_path, 12, 6)
    try:
        assert r_inc.incremental_added == 6
        assert r_inc.incremental_reason is None
        assert r_inc.n_frames_used == r_full.n_frames_used == 18
        assert r_inc.n_offered == 18 and r_inc.n_align_failed == 0
        worst, p999 = _parity(_pixels(r_full.fits_path), _pixels(r_inc.fits_path))
        assert worst < 1e-2, worst
        assert p999 < 5e-3, p999
        # The run record says what happened, and counts every sub in the picture.
        rec = part.run_options(r_inc.run_id)
        assert rec["incremental_added"] == 6 and rec["incremental_base"] == 12
        run = next(r for r in part.proj.iter_stack_runs() if r.id == r_inc.run_id)
        assert run.n_frames_used == 18
        assert run.total_exposure_s == pytest.approx(180.0)
        assert run.rejection_mode == "sigma-clip"
        hdr = fits.getheader(r_inc.fits_path)
        assert hdr["INCRMODE"] == "added" and hdr["INCRADD"] == 6 and hdr["INCRBASE"] == 12
        # …and the state left for next time covers all 18.
        meta = inc.read_meta(part.sidecar)
        assert len(meta["used_ids"]) == 18 and len(meta["welford_ids"]) == 18

        # A further increment reads only the new subs (both κ-σ passes).
        monkeypatch.setattr(stacker_mod, "_align_for_stack", spy)
        new_ids = {part.add(i) for i in range(18, 21)}
        r3 = part.run(_opts())
        assert r3.incremental_added == 3 and r3.n_frames_used == 21
        assert set(aligned) == new_ids and len(aligned) == 2 * len(new_ids)
    finally:
        full.close()
        part.close()


def test_weighted_mean_incremental_matches_a_full_stack(tmp_path):
    """8 + 4 subs, single-pass weighted mean, quality weighting on. Measured:
    max 4.2e-4 of the robust range (the frozen weight yardsticks)."""
    full, part, r_full, r_inc = _run_parity(tmp_path, 8, 4, sigma_clip=False)
    try:
        assert r_inc.incremental_added == 4
        assert r_inc.n_frames_used == r_full.n_frames_used == 12
        worst, _ = _parity(_pixels(r_full.fits_path), _pixels(r_inc.fits_path))
        assert worst < 2e-3, worst
        # The honest per-pixel sub count is exact; the Σ-weight coverage moves by
        # the frozen yardsticks (~1 % here), like the picture does.
        cnt_full = fits.getdata(r_full.fits_path.with_name("master_framecov.fits"))
        cnt_inc = fits.getdata(r_inc.fits_path.with_name("master_framecov.fits"))
        np.testing.assert_array_equal(cnt_inc, cnt_full)
        cov_full = fits.getdata(r_full.fits_path.with_name("master_coverage.fits"))
        cov_inc = fits.getdata(r_inc.fits_path.with_name("master_coverage.fits"))
        np.testing.assert_allclose(cov_inc, cov_full, rtol=2e-2)
    finally:
        full.close()
        part.close()


# ---- fallbacks ---------------------------------------------------------------

def _base(tmp_path, n: int = 4, **kw) -> tuple[_Target, StackOptions]:
    """A small mean-path target, stacked once with the option on."""
    t = _Target(tmp_path, tmp_path / "raws")
    for i in range(n):
        t.add(i)
    opts = _opts(sigma_clip=False, background_flatten=False, **kw)
    first = t.run(opts)
    assert first.incremental_added is None and t.sidecar.is_file()
    return t, opts


def _assert_full(t: _Target, result, n_total: int, reason_part: str,
                 *, state_written: bool = True) -> None:
    assert result.incremental_added is None
    assert result.incremental_reason and reason_part in result.incremental_reason, \
        result.incremental_reason
    assert result.n_frames_used == n_total
    rec = t.run_options(result.run_id)
    assert "incremental_added" not in rec
    assert reason_part in rec["incremental_reason"]
    assert fits.getheader(result.fits_path)["INCRMODE"] == "full"
    assert t.sidecar.is_file() is state_written


def test_changed_options_fall_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        t.add(4)
        r = t.run(replace(opts, hot_pixel_sigma=4.0))
        _assert_full(t, r, 5, "options")
    finally:
        t.close()


def test_post_step_options_do_not_force_a_full_stack(tmp_path):
    """Colour calibration, the final gradient pass and TIFF scaling run on the
    restored sums every time, so changing them keeps the shortcut."""
    t, opts = _base(tmp_path)
    try:
        t.add(4)
        r = t.run(replace(opts, tiff_mode="autostretch", final_gradient_removal=True))
        assert r.incremental_added == 1
    finally:
        t.close()


def test_an_unaccepted_sub_falls_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        t.proj.update_frame(t.ids[2], accept=False)
        t.add(4)
        r = t.run(opts)
        _assert_full(t, r, 4, "no longer accepted")
    finally:
        t.close()


def test_a_remeasured_sub_falls_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        t.proj.update_frame(t.ids[1], fwhm_px=3.3)
        t.add(4)
        r = t.run(opts)
        _assert_full(t, r, 5, "re-solved or re-measured")
    finally:
        t.close()


def test_a_new_reference_falls_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        t.add(4, fwhm=1.2)  # sharper than sub 0 → the new reference
        r = t.run(opts)
        _assert_full(t, r, 5, "reference")
    finally:
        t.close()


def test_a_new_sub_off_the_canvas_falls_back_to_a_full_stack(tmp_path):
    """On a reference canvas a sub pointed most of a field away still stacks
    (cropped), but it is not on the saved canvas, so it can't be continued."""
    t, opts = _base(tmp_path, mosaic_canvas="reference")
    try:
        shifted = make_synth_wcs_text(width=FW, height=FH, ra_center_deg=83.6 + 0.55)
        t.add(4, wcs=shifted)
        r = t.run(opts)
        _assert_full(t, r, r.n_frames_used, "outside the last stack's canvas")
    finally:
        t.close()


def test_missing_or_corrupt_state_falls_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        t.sidecar.unlink()
        t.add(4)
        _assert_full(t, t.run(opts), 5, "no saved state")
        t.sidecar.write_bytes(b"not a zip file at all")
        t.add(5)
        _assert_full(t, t.run(opts), 6, "could not be read")
    finally:
        t.close()


def test_state_for_another_canvas_size_falls_back_to_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        meta = inc.read_meta(t.sidecar)
        bad = {"sum": np.zeros((4, 4, 3), np.float32),
               "weight": np.zeros((4, 4, 3), np.float32),
               "count": np.zeros((4, 4), np.uint32)}
        meta.pop("version", None)
        inc.write_sidecar(t.sidecar, meta, bad, None)
        t.add(4)
        _assert_full(t, t.run(opts), 5, "damaged")
    finally:
        t.close()


def test_no_new_subs_is_a_full_stack(tmp_path):
    t, opts = _base(tmp_path)
    try:
        _assert_full(t, t.run(opts), 4, "no new subs")
    finally:
        t.close()


def test_more_new_subs_than_old_is_a_full_stack(tmp_path):
    t, opts = _base(tmp_path, n=2)
    try:
        for i in range(2, 5):
            t.add(i)
        _assert_full(t, t.run(opts), 5, "full rebuild is the better answer")
    finally:
        t.close()


def test_a_shallow_kappa_sigma_base_is_a_full_stack(tmp_path):
    """Below ``kappa_min_frames`` the old subs' clip couldn't have caught a lone
    trail, so keeping their clip decisions would keep it for good."""
    t = _Target(tmp_path, tmp_path / "raws")
    try:
        for i in range(6):
            t.add(i)
        opts = _opts(background_flatten=False)
        t.run(opts)
        t.add(6)
        _assert_full(t, t.run(opts), 7, "too few")
    finally:
        t.close()


def test_drizzle_always_stacks_in_full_and_saves_no_state(tmp_path):
    pytest.importorskip("drizzle")
    t = _Target(tmp_path, tmp_path / "raws")
    try:
        for i in range(4):
            t.add(i)
        opts = _opts(drizzle=True, drizzle_scale=1.0, background_flatten=False)
        t.run(opts)
        assert not t.sidecar.exists()
        t.add(4)
        _assert_full(t, t.run(opts), 5, "drizzle", state_written=False)
    finally:
        t.close()


def test_a_mosaic_always_stacks_in_full_and_saves_no_state(tmp_path):
    t = _Target(tmp_path, tmp_path / "raws")
    try:
        east = make_synth_wcs_text(width=FW, height=FH, ra_center_deg=83.6 + 0.5)
        for i in range(3):
            t.add(i)
        for i in range(3, 6):
            t.add(i, wcs=east)
            t.proj.update_frame(t.ids[i], ra_center_deg=83.6 + 0.5)
        opts = _opts(sigma_clip=False, background_flatten=False)
        first = t.run(opts)
        assert first.incremental_reason == "mosaics are always rebuilt in full"
        assert not t.sidecar.exists()
    finally:
        t.close()


@pytest.mark.parametrize("change, combine, mosaic, words", [
    ({"drizzle": True}, "drizzle", False, "drizzle"),
    ({"min_max_reject": True}, "min-max-reject", False, "min/max"),
    ({}, "mean", True, "mosaic"),
    ({"mono": True}, "mean", False, "mono"),
    ({"lucky_fraction": 0.5}, "mean", False, "lucky"),
    ({"star_match_unsolved": True}, "mean", False, "star-matched"),
    ({"record_rejection_map": True}, "sigma-clip", False, "rejection map"),
])
def test_unsupported_configurations_are_named(change, combine, mosaic, words):
    why = inc.unsupported_reason(StackOptions(**change), combine,
                                 is_mosaic=mosaic, frames=[])
    assert why is not None and words in why
    assert inc.unsupported_reason(StackOptions(), "sigma-clip",
                                  is_mosaic=False, frames=[]) is None


# ---- off by default, and nothing else changes --------------------------------

def test_off_by_default_writes_nothing_new(tmp_path):
    assert StackOptions().incremental is False
    t = _Target(tmp_path, tmp_path / "raws")
    try:
        for i in range(4):
            t.add(i)
        r = t.run(StackOptions(max_workers=2, background_flatten=False))
        assert not t.sidecar.exists()
        assert r.incremental_added is None and r.incremental_reason is None
        rec = t.run_options(r.run_id)
        assert not any(k.startswith("incremental_") for k in rec)
        assert rec["incremental"] is False
        assert "INCRMODE" not in fits.getheader(r.fits_path)
        leftovers = [p.name for p in (t.proj.project_dir / "output").iterdir()
                     if "incremental" in p.name]
        assert leftovers == []
    finally:
        t.close()


def test_turning_it_on_does_not_change_the_first_picture(tmp_path):
    """The first (full) stack with the option on is pixel-identical to the same
    stack with it off — saving the state only watches."""
    raws = tmp_path / "raws"
    on, off = _Target(tmp_path, raws, "on"), _Target(tmp_path, raws, "off")
    try:
        for i in range(12):
            on.add(i, streak=_streak(i))
            off.add(i, streak=_streak(i))
        # One worker: with several, the float32 sums depend on which thread
        # finishes first, so two identical runs differ in the last bits anyway.
        r_on = on.run(_opts(max_workers=1))
        r_off = off.run(_opts(max_workers=1, incremental=False))
        assert np.array_equal(_pixels(r_on.fits_path), _pixels(r_off.fits_path),
                              equal_nan=True)
    finally:
        on.close()
        off.close()


def test_nothing_is_written_under_incoming(tmp_path):
    """The owner's raw subs live in ``incoming/`` and nowhere else (AGENTS.md
    §10): a full stack, the saved state and an incremental run must leave that
    tree exactly as they found it."""
    incoming = tmp_path / "data" / "incoming" / "M_42"
    t = _Target(tmp_path / "data" / "library", incoming)

    def snapshot() -> dict[str, tuple[int, int]]:
        out = {}
        for root, _dirs, files in os.walk(tmp_path / "data" / "incoming"):
            for name in files:
                st = os.stat(os.path.join(root, name))
                out[os.path.join(root, name)] = (st.st_size, st.st_mtime_ns)
        return out

    try:
        for i in range(6):
            t.add(i)
        before = snapshot()
        opts = _opts(sigma_clip=False)
        t.run(opts)
        t.add(6)
        before[str(_raw(incoming, 6))] = snapshot()[str(_raw(incoming, 6))]
        r = t.run(opts)
        assert r.incremental_added == 1
        assert snapshot() == before
        assert t.sidecar.parent == t.proj.project_dir / "output"
    finally:
        t.close()


# ---- the building blocks -----------------------------------------------------

def test_accumulator_state_round_trip_continues_exactly():
    rng = np.random.default_rng(1)
    frames = [rng.normal(100, 5, (6, 7, 3)).astype(np.float32) for _ in range(5)]
    frames[2][1, 1, :] = np.nan

    ws, wel = WeightedSumAccumulator((6, 7, 3)), WelfordAccumulator((6, 7, 3))
    for k, f in enumerate(frames):
        ws.add_window(f, 0, 0, weight=0.5 + 0.1 * k)
        wel.add_window(f, 0, 0)

    ws2, wel2 = WeightedSumAccumulator((6, 7, 3)), WelfordAccumulator((6, 7, 3))
    for k, f in enumerate(frames[:3]):
        ws2.add_window(f, 0, 0, weight=0.5 + 0.1 * k)
        wel2.add_window(f, 0, 0)
    ws3 = WeightedSumAccumulator.from_state(
        {k: v.copy() for k, v in ws2.state().items()})
    wel3 = WelfordAccumulator.from_state(
        {k: v.copy() for k, v in wel2.state().items()})
    for k, f in enumerate(frames[3:], start=3):
        ws3.add_window(f, 0, 0, weight=0.5 + 0.1 * k)
        wel3.add_window(f, 0, 0)

    np.testing.assert_array_equal(ws3.result(), ws.result())
    np.testing.assert_array_equal(ws3.frame_coverage, ws.frame_coverage)
    np.testing.assert_array_equal(wel3.mean(), wel.mean())
    np.testing.assert_array_equal(wel3.std(), wel.std())
    with pytest.raises(ValueError):
        WeightedSumAccumulator.from_state({
            "sum": np.zeros((2, 2, 3), np.float32),
            "weight": np.zeros((2, 2, 3), np.float32),
            "count": np.zeros((3, 3), np.uint32)})


def test_sidecar_round_trips_through_disk(tmp_path):
    rng = np.random.default_rng(2)
    wsum = {"sum": rng.random((5, 6, 3), dtype=np.float32),
            "weight": rng.random((5, 6, 3), dtype=np.float32),
            "count": rng.integers(0, 9, (5, 6)).astype(np.uint32)}
    wel = {"n": rng.integers(0, 9, (5, 6, 3)).astype(np.uint32),
           "mean": rng.random((5, 6, 3), dtype=np.float32),
           "m2": rng.random((5, 6, 3), dtype=np.float32)}
    spill = inc.spill_welford(tmp_path / "x.welford.part", wel)
    path = inc.write_sidecar(tmp_path / "s_incremental.npz", {"used_ids": [1, 2]},
                             wsum, spill)
    assert not (tmp_path / "s_incremental.npz.part").exists()
    assert inc.read_meta(path)["used_ids"] == [1, 2]
    for k, v in inc.load_wsum_state(path).items():
        np.testing.assert_array_equal(v, wsum[k])
    for k, v in inc.load_welford_state(path).items():
        np.testing.assert_array_equal(v, wel[k])


def _metric_rows(n: int) -> list[FrameRow]:
    return [FrameRow(id=i + 1, source_path=f"/data/x{i}.fit",
                     fwhm_px=2.0 + 0.1 * i, star_count=30 - i,
                     sky_adu_median=1000.0 + 7 * i, transparency_score=1.0 - 0.02 * i,
                     eccentricity_median=0.1 + 0.01 * i) for i in range(n)]


def test_frozen_yardsticks_reproduce_todays_weights_and_scales():
    rows = _metric_rows(9)
    w, _ = compute_frame_weights(rows)
    w_frozen, _ = compute_frame_weights(rows, yardsticks=weight_yardsticks(rows))
    assert w_frozen == w
    s, _ = compute_photometric_scales(rows)
    s_frozen, _ = compute_photometric_scales(
        rows, frozen_reference=photometric_reference(rows))
    assert s_frozen == s
    # …and a frozen yardstick really is frozen: a new, much sharper sub doesn't
    # move the old subs' weights.
    more = rows + [replace(rows[0], id=99, fwhm_px=0.5)]
    w_more, _ = compute_frame_weights(more, yardsticks=weight_yardsticks(rows))
    assert all(w_more[k] == w[k] for k in w)
    with pytest.raises(ValueError):
        compute_frame_weights(rows, yardsticks=weight_yardsticks(rows),
                              group_by_pointing=True)


def test_an_incremental_run_is_no_evidence_for_the_stack_time_estimate():
    from types import SimpleNamespace

    from seestack.stacktime import past_stack

    row = SimpleNamespace(duration_s=60.0, n_frames_used=1000, canvas_w=10,
                          canvas_h=10, engine_version="x",
                          options_json=json.dumps({"incremental_added": 20}))
    assert past_stack(row) is None
    row.options_json = json.dumps({"incremental": True})
    assert past_stack(row) is not None
