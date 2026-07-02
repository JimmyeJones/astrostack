"""The per-run transparency verdict (median transparency of the stacked frames
÷ the target's clear-sky baseline) that drives the "hazy night" badge."""

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import _compute_transparency_ratio


def _add(proj, i, transp, accept=True):
    return proj.add_frame(FrameRow(
        id=None, source_path=f"f{i}.fit", accept=accept,
        transparency_score=transp))


def test_ratio_flags_a_hazy_subset(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # A target whose clearest nights score ~10000; the run being stacked is
        # a hazy subset scoring ~4000, so the ratio should land well below 1.
        clear = [_add(proj, i, 9000 + i * 100) for i in range(6)]  # noqa: F841
        hazy_frames = [FrameRow(id=None, source_path=f"h{j}.fit",
                                transparency_score=t)
                       for j, t in enumerate([3800, 4000, 4200])]
        ratio = _compute_transparency_ratio(proj, hazy_frames)
        assert ratio is not None
        assert ratio < 0.6  # flagged hazy
    finally:
        proj.close()


def test_ratio_is_about_one_for_a_clear_run(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i in range(6):
            _add(proj, i, 10000)
        run = [FrameRow(id=None, source_path=f"r{j}.fit", transparency_score=10000)
               for j in range(4)]
        ratio = _compute_transparency_ratio(proj, run)
        assert ratio is not None
        assert 0.95 <= ratio <= 1.05
    finally:
        proj.close()


def test_ratio_none_without_enough_samples(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Only two scored frames in the whole target — not a meaningful baseline.
        _add(proj, 0, 5000)
        _add(proj, 1, 5000)
        run = [FrameRow(id=None, source_path="r.fit", transparency_score=5000)]
        assert _compute_transparency_ratio(proj, run) is None
    finally:
        proj.close()


def test_ratio_none_when_frames_lack_scores(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i in range(6):
            _add(proj, i, 10000)
        run = [FrameRow(id=None, source_path=f"r{j}.fit", transparency_score=None)
               for j in range(4)]
        assert _compute_transparency_ratio(proj, run) is None
    finally:
        proj.close()
