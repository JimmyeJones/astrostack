"""Workflow export scripts."""

from seestack.io.project import StackRunRow
from seestack.post.export_scripts import write_pixinsight_recipe, write_siril_script
from seestack.stack.stacker import StackOptions


def _run() -> StackRunRow:
    return StackRunRow(
        id=42,
        timestamp_utc="2026-05-12T01:00:00+00:00",
        output_basename="m31_night1",
        fits_path="/proj/output/m31_night1.fits",
        tiff_path="/proj/output/m31_night1.tif",
        preview_path="/proj/output/m31_night1.png",
        n_frames_used=500, canvas_h=1080, canvas_w=1920,
        coverage_min=400, coverage_max=500,
        options_json="{}",
    )


def test_siril_script_includes_load_and_save(tmp_path):
    opts = StackOptions(color_calibration=False)
    path = write_siril_script(_run(), opts, tmp_path / "out.ssf")
    text = path.read_text()
    assert "m31_night1" in text
    assert "load" in text
    assert "save" in text
    assert "pcc" in text  # color cal not done by Seestack → recommended


def test_siril_script_skips_pcc_when_already_done(tmp_path):
    opts = StackOptions(color_calibration=True)
    path = write_siril_script(_run(), opts, tmp_path / "out.ssf")
    text = path.read_text()
    assert "pcc" not in text


def test_pixinsight_recipe_includes_steps(tmp_path):
    opts = StackOptions(color_calibration=False, final_gradient_removal=False)
    path = write_pixinsight_recipe(_run(), opts, tmp_path / "out.js")
    text = path.read_text()
    assert "DynamicBackgroundExtraction" in text
    assert "SpectrophotometricColorCalibration" in text
    assert "Deconvolution" in text
