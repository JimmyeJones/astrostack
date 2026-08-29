"""A read error must reach a *screen*, not just the run's error list.

The stacker has always recorded one raw string per failed read
(``StackResult.errors``) — and nothing in the app has ever displayed that list,
so a night where the NAS share dropped forty reads reached the owner only as an
unexplained thin stack. The run now also counts them: ``n_read_errors`` (how many
distinct subs hit a read error) and ``n_read_recovered`` (how many of those the
*other* pass of a two-pass run read fine and combined anyway, so their light is
in the picture after all), stamped as ``NREADERR``/``NREADREC`` so a finished
master still explains itself long after the job record has rolled.

The count is per **sub**, not per error line: a frame that failed both passes
appears in both passes' logs and must be counted once — that sub is the one the
count most needs to get right, since it really is lost.
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


def _build_project(tmp_path, n: int = 5) -> Project:
    proj = Project.create(tmp_path / "p", name="readerr")
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
            exposure_s=10.0,
        ))
    return proj


def _fail_frame(monkeypatch, stem: str, *, on_pass: int | None = None) -> None:
    """Make one frame's alignment blow up — on one pass, or on every pass.

    ``on_pass`` is 1-based (the passes run in order over the same frames, so the
    n-th call for a file is the n-th pass over it); ``None`` fails every time,
    which is the genuinely-lost sub.
    """
    real = stacker._align_for_stack
    seen: dict[str, int] = {}

    def flaky(frame, *a, **k):
        name = Path(frame.source_path).stem
        if name == stem:
            seen[name] = seen.get(name, 0) + 1
            if on_pass is None or seen[name] == on_pass:
                raise OSError("transient read error")
        return real(frame, *a, **k)

    monkeypatch.setattr(stacker, "_align_for_stack", flaky)


def _header(res) -> dict:
    from astropy.io import fits

    with fits.open(res.fits_path) as hdul:
        return dict(hdul[0].header)


def _two_pass_options() -> StackOptions:
    # sigma_clip with n >= 4 is what selects the two-pass path.
    return StackOptions(sigma_clip=True, max_workers=1, quality_weighted=False,
                        auto_reject=False)


def _single_pass_options() -> StackOptions:
    return StackOptions(sigma_clip=False, max_workers=1, quality_weighted=False,
                        auto_reject=False)


def test_a_sub_that_blipped_once_is_counted_and_credited_as_recovered(
        tmp_path, monkeypatch):
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame(monkeypatch, "f0", on_pass=1)
        res = run_stack(proj, _two_pass_options())
        # Its light is in the picture (pass 2 read it fine)...
        assert res.n_frames_used == 5
        # ...and the storage trouble is still counted, with the reassuring half.
        assert res.n_read_errors == 1
        assert res.n_read_recovered == 1
        hdr = _header(res)
        assert hdr["NREADERR"] == 1
        assert hdr["NREADREC"] == 1
    finally:
        proj.close()


def test_a_sub_that_failed_both_passes_is_counted_once_and_not_recovered(
        tmp_path, monkeypatch):
    """The double-count guard: both passes log the same frame, and it is one sub.

    Counting ``errors`` instead would say two subs hit a read error on a run that
    lost exactly one.
    """
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame(monkeypatch, "f0")
        res = run_stack(proj, _two_pass_options())
        assert res.n_frames_used == 4
        # Two error lines (one per pass) — but one sub.
        assert len([e for e in res.errors if e.startswith("f0.")]) == 2
        assert res.n_read_errors == 1
        assert res.n_read_recovered == 0
        hdr = _header(res)
        assert hdr["NREADERR"] == 1
        assert hdr["NREADREC"] == 0
    finally:
        proj.close()


def test_a_single_pass_run_counts_its_read_errors_too(tmp_path, monkeypatch):
    """A plain weighted-mean stack makes one pass, so nothing can recover — but
    the read failure is exactly as worth reporting."""
    proj = _build_project(tmp_path, n=5)
    try:
        _fail_frame(monkeypatch, "f0")
        res = run_stack(proj, _single_pass_options())
        assert res.n_frames_used == 4
        assert res.n_read_errors == 1
        assert res.n_read_recovered == 0
        assert _header(res)["NREADERR"] == 1
    finally:
        proj.close()


def test_a_healthy_run_records_zero_rather_than_nothing(tmp_path):
    """Stamped at 0 (like NUNREAD) so the card's *absence* means "older master",
    not "no read errors"."""
    proj = _build_project(tmp_path, n=5)
    try:
        res = run_stack(proj, _two_pass_options())
        assert res.errors == []
        assert res.n_read_errors == 0
        assert res.n_read_recovered == 0
        hdr = _header(res)
        assert hdr["NREADERR"] == 0
        assert hdr["NREADREC"] == 0
    finally:
        proj.close()
