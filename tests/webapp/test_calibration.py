"""Calibration master store + endpoints."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from webapp import calibration


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _write_darks(folder: Path, n=4, shape=(8, 8), level=100.0):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        hdu = fits.PrimaryHDU(data=np.full(shape, level, dtype=np.float32))
        hdu.header["EXPTIME"] = 30.0
        hdu.header["GAIN"] = 80.0
        hdu.header["BAYERPAT"] = "RGGB"
        hdu.writeto(folder / f"dark_{i}.fit", overwrite=True)


def test_build_master_bad_source_dir_is_400(client):
    """A non-folder ``source_dir`` is a client error (400), not a 500."""
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": "/no/such/folder/xyz"})
    assert r.status_code == 400
    assert "not a folder" in r.json()["detail"]


def test_build_master_source_dir_that_raises_is_400_not_500(client, monkeypatch):
    """On platforms where ``Path.is_dir()`` *raises* (e.g. an embedded null byte
    → ValueError) rather than returning False, the handler must still answer
    400, not surface a 500 server fault."""
    real_is_dir = Path.is_dir

    def raising_is_dir(self):
        if "\x00" in str(self):
            raise ValueError("embedded null byte")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", raising_is_dir)
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": "ab\x00cd"})
    assert r.status_code == 400
    assert "not a folder" in r.json()["detail"]


def test_store_register_list_resolve_delete(tmp_path):
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    arr = np.full((4, 4), 42.0, dtype=np.float32)
    meta = MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0)
    entry = calibration.register_master(root, name="My Dark", array=arr, meta=meta)
    assert entry["id"] == 1
    assert (calibration.calibration_dir(root) / entry["filename"]).exists()

    listed = calibration.list_masters(root)
    assert len(listed) == 1 and listed[0]["exists"] is True

    dark_path, flat_path, flat_dark_path, bias_path = calibration.resolve_master_paths(root, 1, None)
    assert dark_path and Path(dark_path).exists()
    assert flat_path is None
    assert flat_dark_path is None
    assert bias_path is None

    assert calibration.delete_master(root, 1) is True
    assert calibration.list_masters(root) == []


def test_resolve_unknown_raises(tmp_path):
    import pytest

    with pytest.raises(KeyError):
        calibration.resolve_master_paths(tmp_path / "lib", 999, None)


def test_resolve_flat_dark_master(tmp_path):
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    arr = np.full((4, 4), 5.0, dtype=np.float32)
    flat = calibration.register_master(
        root, name="Flat", array=np.full((4, 4), 100.0, dtype=np.float32),
        meta=MasterMeta("flat", 5, 4, 4, "median"))
    fd = calibration.register_master(
        root, name="FlatDark", array=arr, meta=MasterMeta("dark", 5, 4, 4, "median"))

    dark_path, flat_path, flat_dark_path, bias_path = calibration.resolve_master_paths(
        root, None, flat["id"], fd["id"])
    assert dark_path is None
    assert flat_path and Path(flat_path).exists()
    assert flat_dark_path and Path(flat_dark_path).exists()
    assert bias_path is None


def test_resolve_bias_master(tmp_path):
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    bias = calibration.register_master(
        root, name="Bias", array=np.full((4, 4), 3.0, dtype=np.float32),
        meta=MasterMeta("bias", 0, 4, 4, "median"))

    dark_path, flat_path, flat_dark_path, bias_path = calibration.resolve_master_paths(
        root, None, None, None, bias["id"])
    assert dark_path is None and flat_path is None and flat_dark_path is None
    assert bias_path and Path(bias_path).exists()


def test_recommend_masters_picks_best_match():
    # Two darks at different exposures; the target shot 30 s subs → the 30 s
    # dark must win. Flats are exposure-independent → matched by gain instead.
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 30.0, "gain": 80.0, "exists": True},
        {"id": 2, "kind": "dark", "exposure_s": 120.0, "gain": 80.0, "exists": True},
        {"id": 3, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True},
        {"id": 4, "kind": "flat", "exposure_s": 2.0, "gain": 200.0, "exists": True},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["dark_master_id"] == 1          # exposure-matched dark
    assert rec["flat_master_id"] == 3          # gain-matched flat
    # the well-matched dark scores higher than the exposure-mismatched one
    assert rec["scores"][1] > rec["scores"][2]
    assert rec["scores"][3] > rec["scores"][4]


def test_recommend_masters_suggests_matching_flat_dark():
    # Lights are 30 s; flats are 2 s. The flat-dark must match the *flat's* 2 s
    # exposure, not the lights' 30 s — so the 2 s dark wins as the flat-dark
    # while the 30 s dark wins as the light dark.
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 30.0, "gain": 80.0, "exists": True},
        {"id": 2, "kind": "dark", "exposure_s": 2.0, "gain": 80.0, "exists": True},
        {"id": 3, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["dark_master_id"] == 1        # light dark matches 30 s lights
    assert rec["flat_master_id"] == 3
    assert rec["flat_dark_master_id"] == 2   # flat-dark matches the 2 s flat


def test_recommend_masters_no_flat_dark_when_no_close_exposure():
    # Only a 300 s dark exists; the flat is 2 s. No dark is close enough to be a
    # sensible flat-dark, so none is recommended (rather than a wild mismatch).
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 300.0, "gain": 80.0, "exists": True},
        {"id": 2, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=300.0, gain=80.0)
    assert rec["flat_master_id"] == 2
    assert rec["flat_dark_master_id"] is None


def test_recommend_masters_picks_bias_by_gain():
    # Bias is exposure-independent (zero-second pedestal): matched on gain/temp
    # like a flat. The gain-80 bias must win over the gain-200 one for 80-gain
    # lights.
    masters = [
        {"id": 1, "kind": "bias", "exposure_s": 0.0, "gain": 80.0, "exists": True},
        {"id": 2, "kind": "bias", "exposure_s": 0.0, "gain": 200.0, "exists": True},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["bias_master_id"] == 1
    assert rec["scores"][1] > rec["scores"][2]


def test_recommend_masters_no_bias_when_none_exist():
    masters = [{"id": 1, "kind": "dark", "exposure_s": 30.0, "exists": True}]
    rec = calibration.recommend_masters(masters, exposure_s=30.0)
    assert rec["bias_master_id"] is None


def test_recommend_masters_no_flat_dark_without_flat():
    # A dark but no flat → nothing to attach a flat-dark to.
    masters = [{"id": 1, "kind": "dark", "exposure_s": 2.0, "exists": True}]
    rec = calibration.recommend_masters(masters, exposure_s=30.0)
    assert rec["flat_dark_master_id"] is None


def test_recommend_masters_skips_missing_and_handles_empty():
    # A master whose file is gone must never be recommended.
    masters = [{"id": 1, "kind": "dark", "exposure_s": 30.0, "exists": False}]
    rec = calibration.recommend_masters(masters, exposure_s=30.0)
    assert rec["dark_master_id"] is None
    assert rec["flat_master_id"] is None
    # No masters at all → clean empty result, no crash.
    empty = calibration.recommend_masters([], exposure_s=30.0)
    assert empty["dark_master_id"] is None and empty["scores"] == {}


def _register(root, kind, exposure_s=None, gain=None, sensor_temp_c=None,
              width=4, height=4):
    from seestack.calibrate.masters import MasterMeta
    return calibration.register_master(
        root, name=f"{kind} {exposure_s}",
        array=np.full((height, width), 1.0, dtype=np.float32),
        meta=MasterMeta(kind, 5, width, height, "median", exposure_s=exposure_s,
                        gain=gain, sensor_temp_c=sensor_temp_c))


def test_auto_bind_binds_confident_dark_and_flat(tmp_path):
    """A dark whose exposure matches the subs and a flat are both auto-bound to
    an unattended stack — as on-disk paths, not ids."""
    root = tmp_path / "lib"
    dark = _register(root, "dark", exposure_s=30.0, gain=80.0)
    flat = _register(root, "flat", exposure_s=2.0, gain=80.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert Path(bound["dark_path"]).name == dark["filename"]
    assert Path(bound["flat_path"]).name == flat["filename"]
    # A dark carries the bias, so no separate bias is bound alongside it.
    assert "bias_path" not in bound


def test_auto_bind_skips_exposure_mismatched_dark(tmp_path):
    """The library's only dark is a wild exposure mismatch (300 s dark vs 30 s
    subs) — auto-bind must leave it off rather than over-subtract, while still
    binding the (exposure-independent) flat."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=300.0, gain=80.0)
    flat = _register(root, "flat", exposure_s=2.0, gain=80.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "dark_path" not in bound
    assert Path(bound["flat_path"]).name == flat["filename"]


def test_auto_bind_binds_bias_only_when_no_dark(tmp_path):
    """A bias is only bound for the lights when no dark matched (a dark already
    carries the bias)."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=300.0, gain=80.0)   # mismatched → dropped
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "dark_path" not in bound
    assert Path(bound["bias_path"]).name == bias["filename"]

    # Add a matching dark → the bias is no longer bound (the dark supersedes it).
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert "dark_path" in bound2 and "bias_path" not in bound2


def test_auto_bind_empty_when_no_masters(tmp_path):
    assert calibration.auto_bind_master_paths(
        tmp_path / "lib", [], exposure_s=30.0) == {}


def test_auto_bind_skips_dimension_mismatched_masters(tmp_path):
    """A master built for a different-sized camera must NOT be auto-bound when
    the subs' dimensions are known: binding it would make ``run_stack`` hard-fail
    at ``CalibrationMasters.validate`` — the opposite of auto-bind's "leave
    uncalibrated rather than risk anything" contract. (Regression: before the
    dimension gate the wrong-camera flat/dark were bound and aborted the whole
    unattended stack.)"""
    root = tmp_path / "lib"
    # Library holds masters from an OTHER camera (1000x800), subs are 1920x1080.
    _register(root, "dark", exposure_s=30.0, gain=80.0, width=1000, height=800)
    _register(root, "flat", exposure_s=2.0, gain=80.0, width=1000, height=800)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0, width_px=1920, height_px=1080)
    assert bound == {}  # nothing bound → stack stays uncalibrated, never aborts

    # A same-dimension master IS still bound when the subs' dims match it.
    same = _register(root, "flat", exposure_s=2.0, gain=80.0,
                     width=1920, height=1080)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root),
        exposure_s=30.0, gain=80.0, width_px=1920, height_px=1080)
    assert Path(bound2["flat_path"]).name == same["filename"]


def test_auto_bind_dimension_gate_skipped_when_subs_dims_unknown(tmp_path):
    """When the subs' dimensions are unknown the gate is disabled (unchanged from
    the pre-gate behaviour) — a flat is still bound rather than silently dropped."""
    root = tmp_path / "lib"
    flat = _register(root, "flat", exposure_s=2.0, gain=80.0,
                     width=1000, height=800)
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root),
        exposure_s=30.0, gain=80.0)  # no width_px/height_px passed
    assert Path(bound["flat_path"]).name == flat["filename"]


def test_auto_bind_skips_gain_mismatched_flat(tmp_path):
    """A flat shot at a wildly different gain (a different rig) must NOT be
    auto-bound unattended — dividing by the wrong illumination pattern would
    corrupt the walk-away stack, and there's no human to catch it. (Regression:
    before the flat confidence gate, ``recommend_masters`` always returned the
    only available flat and auto-bind applied it regardless of match quality.)"""
    root = tmp_path / "lib"
    # Subs are gain 80; the library's only flat is gain 400 (a very different rig).
    flat = _register(root, "flat", exposure_s=2.0, gain=400.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "flat_path" not in bound  # left uncalibrated rather than mis-flatted
    # recommend_masters still *offers* it (the interactive form warns a human);
    # only the unattended binder is stricter.
    assert calibration.recommend_masters(
        masters, exposure_s=30.0, gain=80.0)["flat_master_id"] == flat["id"]

    # A same-gain flat clears the gate and is bound as before.
    same = _register(root, "flat", exposure_s=2.0, gain=80.0)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert Path(bound2["flat_path"]).name == same["filename"]


def test_auto_bind_binds_flat_with_unknown_gain_temp(tmp_path):
    """A flat that never recorded gain/temperature still binds — the confidence
    gate only *tightens* on a materially mismatched flat, it must not drop a
    flat whose params are simply unknown (behaviour unchanged from before)."""
    root = tmp_path / "lib"
    flat = _register(root, "flat", exposure_s=2.0)  # no gain / sensor_temp_c
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0,
        sensor_temp_c=-5.0)
    assert Path(bound["flat_path"]).name == flat["filename"]


def test_auto_bind_flat_dark_dropped_with_gain_mismatched_flat(tmp_path):
    """When the flat itself fails the confidence gate, its flat-dark isn't bound
    either (a flat-dark only calibrates a flat that's being applied)."""
    root = tmp_path / "lib"
    _register(root, "flat", exposure_s=2.0, gain=400.0)   # mismatched flat
    _register(root, "dark", exposure_s=2.0, gain=400.0)   # would-be flat-dark
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert "flat_path" not in bound and "flat_dark_path" not in bound


def test_auto_bind_skips_gain_mismatched_bias(tmp_path):
    """A bias shot at a wildly different gain must NOT be auto-bound unattended.
    A master bias carries fixed-pattern structure (readout pedestal, amp glow,
    column offsets) that scales with the camera's gain/offset; the per-frame
    background subtraction removes only the DC offset, not that spatial structure,
    so a wrong-gain bias would leave a mis-scaled pattern in the walk-away stack.
    (Regression: the bias auto-bind had no confidence gate, unlike the dark's
    exposure gate and the flat's gain gate.)"""
    root = tmp_path / "lib"
    # No dark (so the bias would be bound for the lights); the only bias is gain 400.
    bias = _register(root, "bias", exposure_s=0.0, gain=400.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "bias_path" not in bound  # left uncalibrated rather than wrong-pedestal
    # recommend_masters still *offers* it (the interactive form warns a human);
    # only the unattended binder is stricter.
    assert calibration.recommend_masters(
        masters, exposure_s=30.0, gain=80.0)["bias_master_id"] == bias["id"]

    # A same-gain bias clears the gate and is bound as before.
    same = _register(root, "bias", exposure_s=0.0, gain=80.0)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert Path(bound2["bias_path"]).name == same["filename"]


def test_auto_bind_binds_bias_with_unknown_gain_temp(tmp_path):
    """A bias that never recorded gain/temperature still binds — the confidence
    gate only *tightens* on a materially mismatched bias, it must not drop a bias
    whose params are simply unknown (behaviour unchanged from before the gate)."""
    root = tmp_path / "lib"
    bias = _register(root, "bias", exposure_s=0.0)  # no gain / sensor_temp_c
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0,
        sensor_temp_c=-5.0)
    assert Path(bound["bias_path"]).name == bias["filename"]


def test_calibration_suggestions_endpoint(client, solved_library):
    from seestack.calibrate.masters import MasterMeta
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Give this target's frames a known exposure/gain.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, exposure_s=30.0, gain=80.0)
        finally:
            proj.close()
    finally:
        lib.close()

    root = solved_library / "library"
    good = calibration.register_master(
        root, name="Dark 30s", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0, gain=80.0))
    calibration.register_master(
        root, name="Dark 120s", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=120.0, gain=80.0))

    r = client.get(f"/api/targets/{safe}/calibration-suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["exposure_s"] == 30.0
    assert body["dark_master_id"] == good["id"]
    assert body["n_frames"] >= 1


def test_build_master_endpoint(client, data_root, tmp_path):
    darks = tmp_path / "darks"
    _write_darks(darks)

    r = client.post("/api/calibration/masters", json={
        "kind": "dark", "source_dir": str(darks), "name": "Session A",
        "method": "median",
    })
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert job["result"]["kind"] == "dark"
    assert job["result"]["n_frames"] == 4

    listed = client.get("/api/calibration/masters").json()
    assert len(listed) == 1
    mid = listed[0]["id"]
    assert listed[0]["name"] == "Session A"

    # Delete it.
    d = client.delete(f"/api/calibration/masters/{mid}")
    assert d.status_code == 200
    assert client.get("/api/calibration/masters").json() == []


def test_build_master_bad_kind(client, tmp_path):
    darks = tmp_path / "d"
    _write_darks(darks, n=1)
    r = client.post("/api/calibration/masters",
                    json={"kind": "nope", "source_dir": str(darks)})
    assert r.status_code == 400


def test_build_master_missing_dir(client):
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": "/no/such/folder"})
    assert r.status_code == 400


def test_stack_rejects_unknown_master(client, solved_library):
    # Triggering a stack with a non-existent dark master id → 404.
    r = client.post("/api/targets/M_42/stack", json={"dark_master_id": 4242})
    assert r.status_code == 404


def test_stack_with_calibration_master_runs(client, solved_library, tmp_path):
    # Build a master dark matching the solved frames' raw size (320×480) and
    # stack with it — the full resolve → engine path must complete.
    darks = tmp_path / "cdarks"
    _write_darks(darks, n=3, shape=(320, 480), level=5.0)
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": str(darks), "method": "median"})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done"
    mid = client.get("/api/calibration/masters").json()[0]["id"]

    s = client.post("/api/targets/M_42/stack", json={"dark_master_id": mid})
    assert s.status_code == 200
    sjob = _wait_job(client, s.json()["job_id"], timeout=120)
    assert sjob["state"] == "done", sjob
    # The run record should remember which dark was applied.
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
