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

Counting it as used left one loose end, covered here too: the blipped sub's
pass-1 error string stays in the run's error list, so the list reported a failure
for a frame ``NFRAMES`` says was combined. The line is now *qualified* rather than
dropped — a NAS share that drops one read in a hundred is exactly what the list
exists to show, and a frame that failed **both** passes must keep its plain,
unqualified error.
"""

from pathlib import Path

import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("PIL")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import stacker  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    RECOVERED_ERROR_SUFFIX,
    StackOptions,
    _mark_recovered_errors,
    _PassFrameLog,
    run_stack,
)
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
        assert res.errors == []
        assert _header(res)["NFRAMES"] == 5
        assert _header(res)["EXPTOTAL"] == pytest.approx(5 * EXPOSURE_S)
    finally:
        proj.close()


def _lines_for(res, stem: str) -> list[str]:
    return [e for e in res.errors if e.startswith(f"{stem}.")]


def test_the_recovered_subs_error_line_says_it_is_in_the_picture(tmp_path, monkeypatch):
    """The loose end of the count fix: the blip is still reported (a flaking share
    is worth seeing) but no longer reads as a sub that was lost."""
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame_on_pass(monkeypatch, "f0", which_pass=1)
        res = run_stack(proj, _options())
        assert res.n_frames_used == 5
        line = _lines_for(res, "f0")
        assert len(line) == 1, res.errors
        # Still names the file and the underlying read failure...
        assert "transient read error" in line[0]
        assert "OSError" in line[0]
        # ...and now says the frame made it into the picture anyway.
        assert line[0].endswith(RECOVERED_ERROR_SUFFIX)
    finally:
        proj.close()


def test_a_sub_that_failed_pass_two_keeps_its_plain_error(tmp_path, monkeypatch):
    """The real failure the list exists for must never be softened: this sub's
    light genuinely is not in the picture."""
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame_on_pass(monkeypatch, "f0", which_pass=2)
        res = run_stack(proj, _options())
        assert res.n_frames_used == 4
        line = _lines_for(res, "f0")
        assert len(line) == 1, res.errors
        assert not line[0].endswith(RECOVERED_ERROR_SUFFIX)
    finally:
        proj.close()


def test_a_sub_that_failed_both_passes_keeps_both_plain_errors(tmp_path, monkeypatch):
    """A sub whose file is simply unreadable fails twice and is not in the
    picture — neither line may be qualified."""
    proj = _build_project(tmp_path, n=5)
    try:
        real = stacker._align_for_stack

        def always_fails(frame, *a, **k):
            if Path(frame.source_path).stem == "f0":
                raise OSError("transient read error")
            return real(frame, *a, **k)

        monkeypatch.setattr(stacker, "_align_for_stack", always_fails)
        res = run_stack(proj, _options())
        assert res.n_frames_used == 4
        lines = _lines_for(res, "f0")
        assert len(lines) == 2, res.errors
        assert not any(line.endswith(RECOVERED_ERROR_SUFFIX) for line in lines)
    finally:
        proj.close()


# --- the pure re-wording rule, on its own ---------------------------------

def test_mark_recovered_only_touches_a_frame_the_second_pass_combined():
    errors = ["a.fit: OSError: boom", "b.fit: OSError: boom"]
    first = _PassFrameLog(error_slot={1: 0, 2: 1})
    second = _PassFrameLog(used={1})
    assert _mark_recovered_errors(errors, first, second) == 1
    assert errors[0].endswith(RECOVERED_ERROR_SUFFIX)
    assert errors[1] == "b.fit: OSError: boom"


def test_mark_recovered_is_idempotent():
    errors = ["a.fit: OSError: boom"]
    first = _PassFrameLog(error_slot={1: 0})
    second = _PassFrameLog(used={1})
    assert _mark_recovered_errors(errors, first, second) == 1
    assert _mark_recovered_errors(errors, first, second) == 0
    assert errors[0].count(RECOVERED_ERROR_SUFFIX) == 1


def test_mark_recovered_ignores_a_slot_past_the_end_of_the_list():
    """Defensive: a caller that trimmed the list can't make this raise."""
    errors: list[str] = []
    first = _PassFrameLog(error_slot={1: 3})
    second = _PassFrameLog(used={1})
    assert _mark_recovered_errors(errors, first, second) == 0
