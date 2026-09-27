"""A sub the loader cannot read stops counting as one the app can stack.

Observer issue #880: eleven of the owner's targets hold nothing but the
Seestar's own on-device colour output. Every frame is ``accept=1`` and
plate-solved — ASTAP reads a three-plane RGB image happily — but
``load_seestar_raw`` refuses it as a raw Bayer sub, so QC stamps
``qc_error_final:`` and ``build_qc_arglist(only_new=True)`` never offers it
again. Left accepted, those frames still reach the stacker, which errors on them
one at a time and then raises ``drizzle: no usable frames``: seven weeks of
``reprocess_all`` batches failed on exactly those eleven targets, sixty-one
times, with that message.

``seestack.qc.runner.reconcile_unreadable_frames`` is the answer, and it decides
by **reading the file** rather than by trusting the marker — a terminal QC state
can equally mean "the file reads fine and the measurement blew up", and that sub
stacks. Nothing on disk is touched (``AGENTS.md`` §10) and a frame set aside
comes back the moment its file reads again.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.io.scanner import run_qc_and_solve
from seestack.qc.runner import reconcile_unreadable_frames
from seestack.stack.stacker import estimate_stack_basis
from tests.synth import make_synth_wcs_text

_W, _H = 96, 64
_WCS = make_synth_wcs_text(width=_W, height=_H,
                           ra_center_deg=10.0, dec_center_deg=41.0)


def _write_device_output(path) -> None:
    """The Seestar's own finished picture: three planes, not a Bayer mosaic."""
    from astropy.io import fits

    data = np.zeros((3, _H, _W), dtype=np.uint16)
    fits.PrimaryHDU(data).writeto(path, overwrite=True)


def _write_raw_sub(path) -> None:
    """An ordinary 2-D Bayer sub — the shape the loader is happy with."""
    from astropy.io import fits

    hdu = fits.PrimaryHDU(np.full((_H, _W), 100, dtype=np.uint16))
    hdu.header["BAYERPAT"] = "GRBG"
    hdu.writeto(path, overwrite=True)


def _add(proj: Project, path, *, reason: str, accept: bool = True,
         star_count: int | None = None) -> int:
    fid = proj.add_frame(FrameRow(
        source_path=str(path), width_px=_W, height_px=_H,
        wcs_json=_WCS, ra_center_deg=10.0, dec_center_deg=41.0,
    ))
    proj.update_frame(fid, reject_reason=reason, accept=accept,
                      star_count=star_count)
    return fid


def test_a_target_of_only_unreadable_subs_stops_claiming_it_can_be_stacked(tmp_path):
    """The bug, at the seam the owner meets it.

    Before the fix both frames stay accepted, so the stack sizing reports a
    two-frame canvas for a target where nothing can be read — and the run then
    dies deep in the drizzle with ``no usable frames``. After it, the same target
    answers with the plain-language sentence the stacker already had.
    """
    proj = Project.create(tmp_path / "p", name="T (mosaic)")
    try:
        for i in (1, 2):
            f = tmp_path / f"Stacked_{i}.fit"
            _write_device_output(f)
            _add(proj, f, reason="qc_error_final:ValueError: expected 2D Bayer "
                                 "array, got shape (3, 64, 96)")

        set_aside, restored = reconcile_unreadable_frames(proj)
        assert len(set_aside) == 2 and restored == []
        assert [f.id for f in proj.iter_frames(accepted_only=True)] == []
        with pytest.raises(ValueError, match="No accepted frames are plate-solved"):
            estimate_stack_basis(proj)
    finally:
        proj.close()


def test_a_sub_that_reads_fine_is_left_accepted_however_QC_failed_on_it(tmp_path):
    """The carve-out the fix must not break.

    QC catches *every* exception, star detection included, so a terminal marker
    is not evidence the file is unreadable. A sub the loader opens is a sub the
    stack can use, and it stays in.
    """
    proj = Project.create(tmp_path / "p", name="T")
    try:
        good = tmp_path / "Light_1.fit"
        _write_raw_sub(good)
        fid = _add(proj, good, reason="qc_error_final:RuntimeError: internal "
                                      "pixel buffer full")

        assert reconcile_unreadable_frames(proj) == ([], [])
        assert proj.get_frame(fid).accept is True
    finally:
        proj.close()


def test_the_first_retryable_failure_is_never_touched(tmp_path):
    """One NAS blip must not un-accept a sub — only the terminal marker is a
    candidate at all, however unreadable the file is right now."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        f = tmp_path / "Stacked_1.fit"
        _write_device_output(f)
        fid = _add(proj, f, reason="qc_error:OSError: truncated")

        assert reconcile_unreadable_frames(proj) == ([], [])
        assert proj.get_frame(fid).accept is True
    finally:
        proj.close()


def test_a_hand_graded_sub_is_never_un_accepted(tmp_path):
    """A user's own accept is a decision, as everywhere else in this file."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        f = tmp_path / "Stacked_1.fit"
        _write_device_output(f)
        fid = _add(proj, f, reason="qc_error_final:ValueError: nope")
        proj.update_frame(fid, user_override=True)

        assert reconcile_unreadable_frames(proj) == ([], [])
        assert proj.get_frame(fid).accept is True
    finally:
        proj.close()


def test_a_sub_whose_file_is_simply_gone_belongs_to_the_other_verdict(tmp_path):
    """``set_missing_frames_aside`` owns the missing-file case and says so in its
    own words; this reconciler must not take it over."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = _add(proj, tmp_path / "never_written.fit",
                   reason="qc_error_final:FileNotFoundError: nope")

        assert reconcile_unreadable_frames(proj) == ([], [])
        assert proj.get_frame(fid).accept is True
    finally:
        proj.close()


def test_it_is_idempotent_and_leaves_the_reason_it_was_given(tmp_path):
    """The reason is a real state — the QC re-offer skip,
    ``_store_solve_failed_reason``'s carve-out and the rejection summary's
    "couldn't be read" bucket all read that prefix — so only ``accept`` moves."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        f = tmp_path / "Stacked_1.fit"
        _write_device_output(f)
        fid = _add(proj, f, reason="qc_error_final:ValueError: nope")

        assert reconcile_unreadable_frames(proj)[0] == [fid]
        row = proj.get_frame(fid)
        assert row.accept is False
        assert row.reject_reason == "qc_error_final:ValueError: nope"
        assert reconcile_unreadable_frames(proj) == ([], [])
    finally:
        proj.close()


def test_a_sub_set_aside_comes_back_when_its_file_reads_again(tmp_path):
    """What makes the un-accept safe to do unattended: it undoes itself."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        f = tmp_path / "Light_1.fit"
        _write_device_output(f)
        fid = _add(proj, f, reason="qc_error_final:ValueError: nope")
        assert reconcile_unreadable_frames(proj)[0] == [fid]

        # The same path now holds a real sub (the share came back, the file was
        # re-copied): the next scan puts it straight back, reason cleared so QC
        # will measure it.
        _write_raw_sub(f)
        set_aside, restored = reconcile_unreadable_frames(proj)
        assert set_aside == [] and restored == [fid]
        row = proj.get_frame(fid)
        assert row.accept is True
        assert row.reject_reason is None
        assert row.restored_utc
    finally:
        proj.close()


def test_a_sub_some_other_rule_had_already_rejected_is_not_resurrected(tmp_path):
    """The bound on the restore. A frame QC once *measured* carries the metrics
    another rule may have graded it out on, before a later QC failure overwrote
    its reason — so a readable file is not enough to put it back."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        f = tmp_path / "Light_1.fit"
        _write_raw_sub(f)
        fid = _add(proj, f, reason="qc_error_final:OSError: blip",
                   accept=False, star_count=31)

        assert reconcile_unreadable_frames(proj) == ([], [])
        assert proj.get_frame(fid).accept is False
    finally:
        proj.close()


def test_the_scan_reconciles_without_re_reading_a_single_measured_frame(tmp_path):
    """The reconciler is wired into the scan's QC phase.

    ``build_qc_arglist(only_new=True)`` skips terminal frames, so this scan has
    no QC work at all — which is exactly the shape the owner's eleven targets
    have on every one of his scans, and why nothing else would ever reconsider
    them.
    """
    proj = Project.create(tmp_path / "p", name="T (mosaic)")
    try:
        f = tmp_path / "Stacked_1.fit"
        _write_device_output(f)
        fid = _add(proj, f, reason="qc_error_final:ValueError: nope")

        summary = run_qc_and_solve(
            proj, run_qc=True, run_solve=False, serial=True, only_new_qc=True)
        assert summary["qc_total"] == 0
        assert summary["unreadable_set_aside"] == 1
        assert proj.get_frame(fid).accept is False
    finally:
        proj.close()
