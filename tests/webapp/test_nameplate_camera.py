"""The baked caption names the camera the subs were taken with — or none at all.

``_nameplate_fields`` used to pass a module constant, ``_SEESTAR_CAMERA = "ZWO
Seestar S50"``, to the nameplate, the keepsake and every print render, with a
comment citing ``AGENTS.md`` §1 as its authority for a fact that file had never
contained. The owner has an **S30**, so a wrong statement about his gear was
printed onto every picture he shared or printed — a caption is provenance, and
provenance that is confidently wrong is worse than provenance that is absent.

The camera now comes from the stack's own header (``INSTRUME``, stamped from the
subs; else the optics), and a master that says nothing gets **no camera clause**
rather than a guess. Every master written before v0.326.5 is in exactly that
state, and that is the intended behaviour — it heals on the target's next stack.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from seestack.io.project import StackRunRow
from webapp.pipeline import _nameplate_fields

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for synth


class _Entry:
    name = "M 42"


def _run(**kw) -> StackRunRow:
    fields = dict(
        id=1, timestamp_utc="2026-09-02T12:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=505,
        canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
        options_json=json.dumps({}), total_exposure_s=15150.0,
    )
    fields.update(kw)
    return StackRunRow(**fields)


def _master(tmp_path: Path, **cards) -> str:
    """A stack master carrying the provenance cards the caption reads."""
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=np.zeros((3, 8, 8), dtype=np.float32))
    hdu.header["OBJECT"] = "M 42"
    hdu.header["NFRAMES"] = 505
    for key, value in cards.items():
        hdu.header[key.replace("_", "-")] = value
    path = tmp_path / "master.fits"
    hdu.writeto(path, overwrite=True)
    return str(path)


def test_the_caption_names_the_camera_the_master_records(tmp_path):
    plate = _nameplate_fields(
        _master(tmp_path, INSTRUME="ZWO Seestar S30"), _Entry(), _run())
    assert plate.camera == "ZWO Seestar S30"

    from seestack.nameplate import nameplate_line
    assert "ZWO Seestar S30" in nameplate_line(plate)
    assert "S50" not in nameplate_line(plate)


def test_an_s50_master_still_says_s50(tmp_path):
    """The fix is "read it", not "swap one hard-coded model for the other" — an
    owner who really has an S50 must still see an S50."""
    plate = _nameplate_fields(
        _master(tmp_path, INSTRUME="Seestar S50"), _Entry(), _run())
    assert plate.camera == "ZWO Seestar S50"


def test_a_master_with_only_optics_derives_the_model(tmp_path):
    plate = _nameplate_fields(_master(tmp_path, FOCALLEN=150.0), _Entry(), _run())
    assert plate.camera == "ZWO Seestar S30"


def test_a_master_that_names_no_camera_gets_no_camera_clause(tmp_path):
    """The heart of it: silence, not a guess. A pre-v0.326.5 master is this case."""
    from seestack.nameplate import nameplate_line

    plate = _nameplate_fields(_master(tmp_path), _Entry(), _run())
    assert plate.camera is None
    line = nameplate_line(plate)
    assert "Seestar" not in line
    # …and the rest of the caption is untouched — no blank clause, no stray dot.
    assert "M 42" in line
    assert not line.endswith("·")
    assert "··" not in line


def test_an_unreadable_master_never_invents_a_camera():
    plate = _nameplate_fields("/no/such/master.fits", _Entry(), _run())
    assert plate.camera is None
