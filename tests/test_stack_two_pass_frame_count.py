"""A κ-σ run must credit the subs that are actually *in* the picture.

The default (sigma-clipped) stack makes two passes over the frames: pass 1 builds
the per-pixel mean/σ the clip is measured against, pass 2 does the weighted sum
that becomes the image. ``run_stack`` used to record
``n_frames_used = min(n_used_p1, n_used_p2)``, which credits the smaller pass —
so a sub that threw a transient load error in pass 1 (a NAS blip, the exact case
``_kappa_sigma_keep_mask``'s "keep a sample whose reference is unknown" branch
exists for) but loaded fine in pass 2 had its light in the final image and was
still left out of NFRAMES, the integration time, and the align-failure tally.

The honest count is pass 2's: those are the frames whose pixels were summed. A
frame that made pass 1 and *failed* pass 2 contributed nothing and must still be
excluded — that half of ``min()``'s intent is kept by construction.
"""

from pathlib import Path

import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("PIL")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import stacker  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

EXPOSURE_S = 10.0


def _build_project(tmp_path, n: int = 5) -> Project:
    proj = Project.create(tmp_path / "p", name="twopass")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True,
                                  seed=10 + i, n_stars=30)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            exposure_s=EXPOSURE_S,
        ))
    return proj


def _fail_frame_on_pass(monkeypatch, stem: str, which_pass: int) -> None:
    """Make one frame's alignment blow up on exactly one of the two passes.

    ``which_pass`` is 1-based; the passes run in order over the same frames, so
    the n-th call for a given file is the n-th pass over it.
    """
    real = stacker._align_for_stack
    seen: dict[str, int] = {}

    def flaky(frame, *a, **k):
        name = Path(frame.source_path).stem
        if name == stem:
            seen[name] = seen.get(name, 0) + 1
            if seen[name] == which_pass:
                raise OSError("transient read error")
        return real(frame, *a, **k)

    monkeypatch.setattr(stacker, "_align_for_stack", flaky)


def _header(res) -> dict:
    from astropy.io import fits

    with fits.open(res.fits_path) as hdul:
        return dict(hdul[0].header)


def _options() -> StackOptions:
    # sigma_clip with n >= 4 is what selects the two-pass path.
    return StackOptions(sigma_clip=True, max_workers=1, quality_weighted=False,
                        auto_reject=False)


def test_a_sub_that_blipped_in_pass_one_is_still_counted(tmp_path, monkeypatch):
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame_on_pass(monkeypatch, "f0", which_pass=1)
        res = run_stack(proj, _options())
        # Pass 1 saw 4 frames, pass 2 combined all 5 — and all 5 are in the image.
        assert res.n_frames_used == 5
        assert res.n_align_failed == 0
        assert _header(res)["NFRAMES"] == 5
        assert _header(res)["NALIGNFL"] == 0
        # The integration time the owner reads is n_used x the per-sub exposure,
        # so it under-reported by a whole sub too.
        assert _header(res)["EXPTOTAL"] == pytest.approx(5 * EXPOSURE_S)
    finally:
        proj.close()


def test_a_sub_that_failed_pass_two_is_not_counted(tmp_path, monkeypatch):
    """The fail-safe half of the old ``min()``, kept: pass 2 is what makes the
    picture, so a frame missing from it contributed nothing and must not be
    credited."""
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame_on_pass(monkeypatch, "f0", which_pass=2)
        res = run_stack(proj, _options())
        assert res.n_frames_used == 4
        assert res.n_align_failed == 1
        assert _header(res)["EXPTOTAL"] == pytest.approx(4 * EXPOSURE_S)
    finally:
        proj.close()


def test_an_ordinary_two_pass_run_is_unchanged(tmp_path):
    """No divergence between the passes → the number the owner has always seen."""
    proj = _build_project(tmp_path, n=5)
    try:
        res = run_stack(proj, _options())
        assert res.n_frames_used == 5
        assert res.n_align_failed == 0
        assert _header(res)["NFRAMES"] == 5
        assert _header(res)["EXPTOTAL"] == pytest.approx(5 * EXPOSURE_S)
    finally:
        proj.close()
