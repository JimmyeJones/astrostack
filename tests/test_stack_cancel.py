"""Cancelling a stack must return a graceful ``StackResult(cancelled=True)``,
never raise.

The drizzle two-pass path guards its "no usable frames" error with
``and not cancel()`` (``stacker.py`` ~line 1107); the standard κ-σ / min-max /
single-pass branches used to omit that clause. Because ``sigma_clip`` is the
**default**, a routine user cancel of an ordinary stack hit the bug: a cancel
*during* pass 1 leaves ``n_used_p1 > 0`` but makes pass 2 break on its very
first frame (``n_used_p2 == 0`` → ``n_used == 0``), so the pass-2 zero-guard
raised ``ValueError("pass 2 produced no usable frames")`` instead of reaching
the cancelled-result return. The job then surfaced as a red *error* rather than
a clean *cancelled*. A cancel before the first frame completes hit the same flaw
in the pass-1 / min-max / single-pass guards.

These tests fail-before (``run_stack`` raises ``ValueError``) and pass-after
(returns ``cancelled=True``) across every rejection path.
"""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n: int = 4) -> Project:
    proj = Project.create(tmp_path / "p", name="cancel")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=10 + i, n_stars=30,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def test_sigma_clip_cancel_before_first_frame_returns_cancelled(tmp_path):
    # sigma_clip is the DEFAULT. Cancel from the very start → pass 1 breaks on
    # its first frame (n_used_p1 == 0). Before the fix the pass-1 guard raised;
    # now it defers to the graceful cancelled return.
    proj = _build_project(tmp_path)
    assert StackOptions().sigma_clip is True  # guard the "default" premise
    res = run_stack(
        proj, options=StackOptions(max_workers=1),
        cancel=lambda: True, progress=lambda *a, **k: None,
    )
    assert res.cancelled is True


def test_sigma_clip_cancel_during_pass1_returns_cancelled(tmp_path):
    # The realistic case: the user cancels partway through pass 1 (≥1 frame
    # already consumed → n_used_p1 > 0), so pass 2 breaks immediately
    # (n_used_p2 == 0). This is the exact path the pass-2 guard mishandled.
    proj = _build_project(tmp_path)
    calls = {"n": 0}

    def cancel_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # False on the 1st check, True afterwards

    res = run_stack(
        proj, options=StackOptions(max_workers=1),
        cancel=cancel_after_first, progress=lambda *a, **k: None,
    )
    assert res.cancelled is True


def test_min_max_reject_cancel_returns_cancelled(tmp_path):
    proj = _build_project(tmp_path)
    res = run_stack(
        proj, options=StackOptions(max_workers=1, min_max_reject=True),
        cancel=lambda: True, progress=lambda *a, **k: None,
    )
    assert res.cancelled is True


def test_single_pass_cancel_returns_cancelled(tmp_path):
    proj = _build_project(tmp_path)
    res = run_stack(
        proj, options=StackOptions(max_workers=1, sigma_clip=False),
        cancel=lambda: True, progress=lambda *a, **k: None,
    )
    assert res.cancelled is True
