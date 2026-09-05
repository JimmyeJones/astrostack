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


def test_build_master_job_reports_skipped_frames(client, tmp_path):
    """A build from a folder mixing good frames with a wrong-size and an
    unreadable one finishes `done` with the good frames combined and a
    plain-language skip accounting in the job result — so the Jobs page can tell
    the user how many of their frames were actually used, not just 'done'."""
    src = tmp_path / "darks"
    _write_darks(src, n=3, shape=(8, 8))              # three good frames
    # one wrong-size frame + one unreadable file in the same folder
    fits.PrimaryHDU(data=np.full((4, 4), 100.0, dtype=np.float32)).writeto(
        src / "wrong.fit", overwrite=True)
    (src / "bad.fit").write_bytes(b"not a fits file")

    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": str(src)})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done"
    result = body["result"]
    assert result["n_frames"] == 3                    # only the good frames combined
    assert result["n_skipped"] == 2
    assert result["skipped_buckets"] == {"wrong size": 1, "unreadable": 1}


def test_build_master_job_reports_zero_skipped_on_a_clean_set(client, tmp_path):
    src = tmp_path / "flats"
    _write_darks(src, n=3, shape=(8, 8))
    r = client.post("/api/calibration/masters",
                    json={"kind": "flat", "source_dir": str(src)})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done"
    assert body["result"]["n_skipped"] == 0
    assert body["result"]["skipped_buckets"] == {}
    # A small set is combined whole, so the supplied count matches — the Jobs
    # page reads the two being equal as "nothing was dropped" and says nothing
    # about sampling.
    assert body["result"]["n_supplied"] == 3


def test_build_master_job_reports_the_supplied_count_when_the_set_is_sampled(
    client, tmp_path, monkeypatch,
):
    """A very large dark/flat set is evenly sampled down to a memory bound before
    combining. That was only ever written to the log, so a beginner who dropped
    200 darks read "built from 64 frames" with no way to tell whether 136 had
    failed. The job result now carries how many they actually gave."""
    from seestack.calibrate import masters as masters_mod

    real_build = masters_mod.build_master

    def small_bound(*args, **kwargs):
        kwargs["max_frames"] = 2
        return real_build(*args, **kwargs)

    monkeypatch.setattr(masters_mod, "build_master", small_bound)

    src = tmp_path / "many_darks"
    _write_darks(src, n=5, shape=(8, 8))
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": str(src)})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done"
    result = body["result"]
    assert result["n_supplied"] == 5      # what the user pointed at
    assert result["n_frames"] == 2        # what the memory bound combined
    assert result["n_skipped"] == 0       # sampling is not a skip


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


def test_master_ids_are_never_reused_after_deletion(tmp_path):
    """A stack run persists the server-resolved calibration *path*
    (``.../dark_1.fits``) in its options, so a master id/filename is a permanent
    reference. Deleting the newest master and rebuilding must NOT reuse its
    id/filename — otherwise an old run's recorded dark silently rebinds to a
    different master's pixels and an unattended *Reprocess everything*
    miscalibrates. Regression for the ``_next_id = max(current)+1`` id-reuse bug.
    """
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    a = calibration.register_master(
        root, name="DarkA",
        array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=10.0),
    )
    assert a["id"] == 1 and a["filename"] == "dark_1.fits"
    a_path = calibration.master_path(root, 1)

    # Delete the newest (here only) master, then build a *different* one.
    assert calibration.delete_master(root, a["id"]) is True
    b = calibration.register_master(
        root, name="DarkB",
        array=np.full((4, 4), 999.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0),
    )
    # Its id and filename must be fresh — never dark_1.fits again.
    assert b["id"] == 2, "master id was reused after deletion"
    assert b["filename"] == "dark_2.fits"
    # A run that recorded the old path must NOT now resolve to B's pixels.
    assert calibration.master_id_for_path(root, str(a_path)) is None
    assert calibration.master_path(root, 2) is not None

    # Even after deleting *every* master (empty registry), ids keep climbing —
    # the persisted high-water mark, not the registry max, is what guarantees it.
    assert calibration.delete_master(root, b["id"]) is True
    assert calibration.list_masters(root) == []
    c = calibration.register_master(
        root, name="DarkC",
        array=np.full((4, 4), 7.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=20.0),
    )
    assert c["id"] == 3 and c["filename"] == "dark_3.fits"


def test_master_id_high_water_falls_back_to_registry_max_when_absent(tmp_path):
    """An older library with no persisted counter (or a downgrade that never
    wrote one) must still allocate correctly from the registry max — the counter
    is an extra guard, never the sole source of the next id."""
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    calibration.register_master(
        root, name="D1", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=10.0),
    )
    # Simulate an old library: drop the sidecar counter but keep masters.json.
    (calibration.calibration_dir(root) / calibration.NEXT_ID_NAME).unlink()
    b = calibration.register_master(
        root, name="D2", array=np.full((4, 4), 2.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=20.0),
    )
    assert b["id"] == 2 and b["filename"] == "dark_2.fits"


def test_concurrent_register_and_delete_stay_consistent(tmp_path, monkeypatch):
    """A master build (``register_master``, on the job worker) and a master
    deletion (``delete_master``, on the request threadpool) run concurrently.

    Regression: both did an unlocked read → mutate → write, so an interleave
    dropped one side's change — a just-built master vanished from the registry
    (its ``.fits`` orphaned) or a deleted one was resurrected. With the shared
    ``_REGISTRY_LOCK`` the two sequences serialise, so the outcome is always the
    consistent one: the old master gone (file + entry) and the new one present
    (file + entry). We widen the read→write window with a delayed write so an
    unlocked implementation reliably loses the race."""
    import threading

    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    old = calibration.register_master(
        root, name="Old", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0))
    old_file = calibration.calibration_dir(root) / old["filename"]
    assert old_file.exists()

    orig_write = calibration._write_registry

    def slow_write(library_root, entries):
        time.sleep(0.05)  # widen the race window between read and write
        return orig_write(library_root, entries)

    monkeypatch.setattr(calibration, "_write_registry", slow_write)

    start = threading.Barrier(2)
    new_entry: dict = {}

    def do_register():
        start.wait()
        new_entry.update(calibration.register_master(
            root, name="New", array=np.full((4, 4), 2.0, dtype=np.float32),
            meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=60.0)))

    def do_delete():
        start.wait()
        calibration.delete_master(root, old["id"])

    t1 = threading.Thread(target=do_register)
    t2 = threading.Thread(target=do_delete)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # The outcome must be internally consistent: exactly the new master
    # registered, every registered entry's file present, and no orphaned files
    # on disk. (An unlocked race instead loses the register — leaving an
    # orphaned .fits with no entry — or resurrects the delete, leaving an entry
    # whose file was unlinked. Filenames are id-derived so the surviving master
    # may reuse the old id/filename; the invariant is registry↔disk agreement,
    # not a specific filename.)
    listed = calibration.list_masters(root)
    assert [e["name"] for e in listed] == ["New"], listed
    cal_dir = calibration.calibration_dir(root)
    registered_files = {e["filename"] for e in listed}
    for fn in registered_files:
        assert (cal_dir / fn).exists(), f"registered master {fn} has no file"
    on_disk = {p.name for p in cal_dir.glob("*.fits")}
    assert on_disk == registered_files, (on_disk, registered_files)


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


def test_recommend_masters_skips_a_flat_dark_the_flat_cannot_use():
    # A flat-dark is subtracted from the *flat*, and the engine compares the two
    # shapes: a mismatch is skipped silently, leaving the flat with its own
    # pedestal in it. Recommending the exposure-perfect-but-wrong-size dark would
    # put that silent mismatch on the form behind a ★, so the usable dark wins
    # even though it ranks further away.
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 2.0, "gain": 80.0, "exists": True,
         "width_px": 240, "height_px": 160},   # perfect match, wrong camera
        {"id": 2, "kind": "dark", "exposure_s": 2.5, "gain": 80.0, "exists": True,
         "width_px": 480, "height_px": 320},   # further, but usable
        {"id": 3, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True,
         "width_px": 480, "height_px": 320},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["flat_master_id"] == 3
    assert rec["flat_dark_master_id"] == 2


def test_recommend_masters_no_flat_dark_when_every_one_is_the_wrong_size():
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 2.0, "gain": 80.0, "exists": True,
         "width_px": 240, "height_px": 160},
        {"id": 2, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True,
         "width_px": 480, "height_px": 320},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["flat_master_id"] == 2
    assert rec["flat_dark_master_id"] is None


def test_recommend_masters_flat_dark_size_gate_is_one_sided():
    # A master built before dimensions were recorded, or a flat that never
    # recorded its own, can't be disproved — so nothing changes on upgrade.
    for dark_dims, flat_dims in (
        ({}, {"width_px": 480, "height_px": 320}),
        ({"width_px": 240, "height_px": 160}, {}),
        ({"width_px": None, "height_px": None}, {"width_px": 480, "height_px": 320}),
    ):
        masters = [
            {"id": 1, "kind": "dark", "exposure_s": 2.0, "gain": 80.0,
             "exists": True, **dark_dims},
            {"id": 2, "kind": "flat", "exposure_s": 2.0, "gain": 80.0,
             "exists": True, **flat_dims},
        ]
        rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
        assert rec["flat_dark_master_id"] == 1


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
              width=4, height=4, bayer_pattern=None):
    from seestack.calibrate.masters import MasterMeta
    return calibration.register_master(
        root, name=f"{kind} {exposure_s}",
        array=np.full((height, width), 1.0, dtype=np.float32),
        meta=MasterMeta(kind, 5, width, height, "median", exposure_s=exposure_s,
                        gain=gain, sensor_temp_c=sensor_temp_c,
                        bayer_pattern=bayer_pattern))


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
    # A gain-mismatched dark is dropped outright (not scalable — its gain is wrong,
    # so exposure-scaling wouldn't fix it); the bias is bound for the lights.
    _register(root, "dark", exposure_s=300.0, gain=400.0)  # gain-mismatched → dropped
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "dark_path" not in bound
    assert "scale_dark_to_light" not in bound
    assert Path(bound["bias_path"]).name == bias["filename"]

    # Add a matching dark → the bias is no longer bound (the dark supersedes it).
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert "dark_path" in bound2 and "bias_path" not in bound2


def test_auto_bind_scales_exposure_mismatched_dark_via_bias(tmp_path):
    """A dark that matches gain/temperature but *not* exposure is recovered by
    exposure-scaling when a confident master bias is available — the unattended
    equivalent of the Stack form's "select your master bias and scale the dark".
    The bias is consumed by the scaling (``bias + (dark − bias)·t_light/t_dark``),
    not bound as a separate light-frame bias, so this beats the bias-only fallback
    (it recovers the thermal signal a bare bias can't)."""
    root = tmp_path / "lib"
    # Subs are 10 s / gain 80; the dark is a same-gain 30 s (exposure mismatch), and
    # a matching master bias is present → scale the dark to 10 s.
    dark = _register(root, "dark", exposure_s=30.0, gain=80.0)
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=10.0, gain=80.0)
    assert Path(bound["dark_path"]).name == dark["filename"]
    assert Path(bound["bias_path"]).name == bias["filename"]
    assert bound["scale_dark_to_light"] is True


def test_auto_bind_no_dark_scaling_without_a_bias(tmp_path):
    """A gain-matched but exposure-mismatched dark is left off entirely when there
    is no master bias to scale it with — the stack stays dark-uncalibrated exactly
    as before Task 2 (never a bare mismatched-exposure dark)."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0)  # right gain, wrong exposure
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=10.0, gain=80.0)
    assert "dark_path" not in bound
    assert "scale_dark_to_light" not in bound


def test_auto_bind_no_scaling_when_dark_gain_mismatched(tmp_path):
    """Exposure-scaling requires the dark's *gain* to confidently match too — a
    dark that mismatches on both exposure and gain is never scaled (scaling can't
    fix a wrong gain), so it drops through to the ordinary bias-only fallback."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=400.0)  # wrong gain AND exposure
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=10.0, gain=80.0)
    assert "dark_path" not in bound
    assert "scale_dark_to_light" not in bound
    assert Path(bound["bias_path"]).name == bias["filename"]


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


def test_auto_bind_skips_gain_mismatched_dark(tmp_path):
    """A dark whose exposure matches the subs but whose gain is a wild mismatch
    (a different rig) must NOT be auto-bound unattended — a dark encodes the
    gain-dependent bias pedestal, so a wrong-gain dark over-/under-subtracts even
    at the right exposure, and there's no human to catch it. (Regression: before
    the dark confidence gate the dark was bound on exposure alone, unlike the
    flat's and bias's gain gates.)"""
    root = tmp_path / "lib"
    # Subs are gain 80; the only dark is a same-exposure but gain-400 (other rig).
    dark = _register(root, "dark", exposure_s=30.0, gain=400.0)
    masters = calibration.list_masters(root)

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0)
    assert "dark_path" not in bound  # left uncalibrated rather than mis-subtracted
    # recommend_masters still *offers* it (the interactive form warns a human);
    # only the unattended binder is stricter.
    assert calibration.recommend_masters(
        masters, exposure_s=30.0, gain=80.0)["dark_master_id"] == dark["id"]

    # A same-gain dark clears the gate and is bound as before.
    same = _register(root, "dark", exposure_s=30.0, gain=80.0)
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0)
    assert Path(bound2["dark_path"]).name == same["filename"]


def test_auto_bind_binds_dark_with_unknown_gain_temp(tmp_path):
    """A dark that never recorded gain/temperature still binds when its exposure
    matches — the confidence gate only *tightens* on a materially mismatched gain,
    it must not drop a dark whose gain/temperature are simply unknown (behaviour
    unchanged from before the gate)."""
    root = tmp_path / "lib"
    dark = _register(root, "dark", exposure_s=30.0)  # no gain / sensor_temp_c
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0,
        sensor_temp_c=-5.0)
    assert Path(bound["dark_path"]).name == dark["filename"]


def test_auto_bind_recovers_a_scalable_dark_when_the_top_pick_fails_its_gate(tmp_path):
    """The library's *closest* dark (exposure-perfect but a wrong gain) fails the
    gain confidence gate, while a further-ranked dark matches gain/temperature and
    — with a master bias present — is exposure-scalable to the subs. Auto-bind must
    fall through to that usable dark instead of giving up on the single top-ranked
    pick, so the walk-away stack keeps its dark calibration. (Regression: before
    ranking darks by bindability, a gain-mismatched-but-exposure-perfect dark
    masked a gain-matched scalable one, leaving the stack uncalibrated.)"""
    root = tmp_path / "lib"
    # Subs: 10 s / gain 80.
    # Dark A — exposure-perfect (10 s) but gain 200 (a different rig). Its combined
    # match distance is the lowest (the exposure term, weighted ×3, is zero), so
    # recommend_masters returns it as the top pick — but it fails the gain gate.
    _register(root, "dark", exposure_s=10.0, gain=200.0)
    # Dark B — gain-matched (80) but 30 s (exposure mismatch): further by distance,
    # yet scalable to 10 s via the bias.
    dark_b = _register(root, "dark", exposure_s=30.0, gain=80.0)
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)
    masters = calibration.list_masters(root)

    # Precondition: the top-ranked dark really is the exposure-perfect (but
    # gain-mismatched) A, not the scalable B — so this exercises the fallthrough.
    rec = calibration.recommend_masters(masters, exposure_s=10.0, gain=80.0)
    assert rec["dark_master_id"] != dark_b["id"]

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=10.0, gain=80.0)
    assert Path(bound["dark_path"]).name == dark_b["filename"]
    assert Path(bound["bias_path"]).name == bias["filename"]
    assert bound["scale_dark_to_light"] is True


def test_auto_bind_still_uncalibrated_when_no_dark_is_bindable(tmp_path):
    """The fallthrough only ever binds a *confident* dark: when the top pick fails
    its gate and no other dark qualifies either, the stack stays dark-uncalibrated
    (the safe direction), never a bare mismatched dark. Here the second dark is
    gain-matched but exposure-mismatched with NO bias to scale it — so unbindable."""
    root = tmp_path / "lib"
    # A: exposure-perfect, gain-mismatched (fails the gain gate).
    _register(root, "dark", exposure_s=10.0, gain=200.0)
    # B: gain-matched but exposure-mismatched, and no bias exists to scale it.
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root), exposure_s=10.0, gain=80.0)
    assert "dark_path" not in bound
    assert "scale_dark_to_light" not in bound
    assert "bias_path" not in bound


def _fake_proj_with_frames(exposure_s=30.0, gain=80.0, width=4, height=4,
                           bayer_pattern="RGGB"):
    """A minimal stand-in for a Project exposing ``iter_frames`` for
    ``_auto_bind_calibration`` — just the frame attributes it reads."""
    from types import SimpleNamespace

    frame = SimpleNamespace(exposure_s=exposure_s, gain=gain, sensor_temp_c=None,
                            width_px=width, height_px=height,
                            bayer_pattern=bayer_pattern)

    class _Proj:
        def iter_frames(self, accepted_only=False):  # noqa: ARG002
            return [frame, frame]

    return _Proj()


def test_auto_bind_clears_a_stray_scale_dark_to_light_flag(tmp_path):
    """A leftover ``scale_dark_to_light=True`` in the global defaults (a bool flag
    survives the calibration-path strip) must be cleared when auto-bind binds a
    plain matched-exposure dark with no bias — otherwise the engine is asked to
    exposure-scale a dark it has no bias to scale against. (Tidiness/autonomy: the
    engine no-ops the scaling, but the run's calibration intent is misrepresented.)"""
    from types import SimpleNamespace

    from webapp.pipeline import _auto_bind_calibration

    root = tmp_path / "lib"
    dark = _register(root, "dark", exposure_s=30.0, gain=80.0)
    settings = SimpleNamespace(resolved_library_root=root)
    proj = _fake_proj_with_frames(exposure_s=30.0, gain=80.0)

    # Global default carried the flag with no dark; the path strip keeps the bool.
    opts = {"scale_dark_to_light": True}
    _auto_bind_calibration(settings, proj, opts)

    assert Path(opts["dark_path"]).name == dark["filename"]  # a plain dark was bound
    assert "bias_path" not in opts
    assert "scale_dark_to_light" not in opts  # the stray flag was cleared


def test_auto_bind_keeps_scale_dark_to_light_when_it_binds_a_bias_scaled_dark(tmp_path):
    """The clearing is precise: when auto-bind *itself* binds a bias-scaled dark
    (exposure mismatch recovered via a confident bias), the flag it set stays."""
    from types import SimpleNamespace

    from webapp.pipeline import _auto_bind_calibration

    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    _register(root, "bias", exposure_s=0.0, gain=80.0)
    settings = SimpleNamespace(resolved_library_root=root)
    proj = _fake_proj_with_frames(exposure_s=10.0, gain=80.0)  # exposure mismatch

    opts: dict = {}
    _auto_bind_calibration(settings, proj, opts)

    assert "dark_path" in opts and "bias_path" in opts
    assert opts["scale_dark_to_light"] is True


def test_auto_bind_clears_a_stray_flag_even_when_no_dark_binds(tmp_path):
    """When no master binds at all, a stray ``scale_dark_to_light`` (no dark to
    scale) is still meaningless and gets cleared."""
    from types import SimpleNamespace

    from webapp.pipeline import _auto_bind_calibration

    root = tmp_path / "lib"  # empty library — nothing to bind
    root.mkdir(parents=True, exist_ok=True)
    settings = SimpleNamespace(resolved_library_root=root)
    proj = _fake_proj_with_frames(exposure_s=30.0, gain=80.0)

    opts = {"scale_dark_to_light": True}
    _auto_bind_calibration(settings, proj, opts)

    assert "dark_path" not in opts
    assert "scale_dark_to_light" not in opts


def test_auto_bind_recovers_a_flat_when_the_top_pick_fails_its_gate(tmp_path):
    """The closest flat by match distance is from a different-sized camera, so it
    fails the dimension gate, while a slightly-further same-dimension flat binds
    cleanly. Auto-bind must fall through to that usable flat instead of leaving the
    stack flat-uncalibrated on the single top-ranked pick — mirroring the dark
    path. (Regression: the flat binder keyed off only ``recommend_masters``' top
    flat, so a top-ranked-but-unbindable flat masked a bindable one.)"""
    root = tmp_path / "lib"
    # Subs: 1920×1080, gain 80. Flat A is the exact-gain top pick but wrong-size;
    # Flat B is a hair further (gain 81) but the right size.
    _register(root, "flat", exposure_s=2.0, gain=80.0, width=1000, height=800)
    flat_b = _register(root, "flat", exposure_s=2.0, gain=81.0,
                       width=1920, height=1080)
    masters = calibration.list_masters(root)

    # Precondition: the top-ranked flat really is the wrong-size A, so this
    # exercises the fallthrough rather than just picking B outright.
    rec = calibration.recommend_masters(masters, gain=80.0)
    assert rec["flat_master_id"] != flat_b["id"]

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0, width_px=1920, height_px=1080)
    assert Path(bound["flat_path"]).name == flat_b["filename"]


def test_auto_bind_recovers_a_bias_when_the_top_pick_fails_its_gate(tmp_path):
    """Same fallthrough for the bias: the closest bias is a different-sized
    camera's (fails the dimension gate) while a slightly-further same-dimension
    bias binds. With no dark present the usable bias must still be found for the
    lights instead of being masked by the top-ranked unbindable one."""
    root = tmp_path / "lib"
    # No dark, so the bias is bound for the lights. Bias A: exact-gain but wrong
    # size (top pick); Bias B: a hair further (gain 81) but the right size.
    _register(root, "bias", exposure_s=0.0, gain=80.0, width=1000, height=800)
    bias_b = _register(root, "bias", exposure_s=0.0, gain=81.0,
                       width=1920, height=1080)
    masters = calibration.list_masters(root)

    rec = calibration.recommend_masters(masters, gain=80.0)
    assert rec["bias_master_id"] != bias_b["id"]

    bound = calibration.auto_bind_master_paths(
        root, masters, exposure_s=30.0, gain=80.0, width_px=1920, height_px=1080)
    assert "dark_path" not in bound
    assert Path(bound["bias_path"]).name == bias_b["filename"]


def test_diagnose_advises_a_bias_for_a_gain_matched_exposure_mismatched_dark(tmp_path):
    """The one still-uncalibrated dark signature after v0.103.12: a gain-matching
    dark at the wrong exposure with no bias to scale it — advise building a bias."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0)  # right gain, wrong exposure
    advice = calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0)
    assert advice is not None
    assert "master bias" in advice
    assert "30s" in advice and "10s" in advice


def test_diagnose_none_when_a_confident_bias_exists(tmp_path):
    """With a confident master bias the exposure-mismatched dark would be scaled
    (v0.103.12) and the stack wouldn't be uncalibrated — so no advice fires."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    _register(root, "bias", exposure_s=0.0, gain=80.0)
    assert calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0) is None


def test_diagnose_none_when_the_dark_exposure_matches(tmp_path):
    """A dark whose exposure matches would have been bound directly — no advice."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=10.0, gain=80.0)
    assert calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0) is None


def test_diagnose_none_when_the_dark_gain_mismatches(tmp_path):
    """A dark from a genuinely different rig (wrong gain) isn't confidently the
    user's dark — building a bias wouldn't recover it, so give no bias advice."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=400.0)  # wrong gain AND exposure
    assert calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0) is None


def test_diagnose_none_without_a_dark_or_exposure(tmp_path):
    """No matching dark, or an unknown sub exposure, yields no specific advice."""
    root = tmp_path / "lib"
    _register(root, "flat", exposure_s=2.0, gain=80.0)  # only a flat
    assert calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0) is None
    # A dark present but the subs' exposure is unknown → can't judge the mismatch.
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    assert calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=None, gain=80.0) is None


def test_diagnose_flags_a_wrong_camera_dark(tmp_path):
    """The library visibly holds a dark, yet the stack came out uncalibrated —
    because that dark was built at another frame size and is refused outright.
    The generic "build or pick a master" copy reads as a bug in that state."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=10.0, gain=80.0, width=1080, height=1920)

    advice = calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0,
        width_px=480, height_px=320)

    assert advice is not None
    assert "1080×1920" in advice and "480×320" in advice
    assert "binning" in advice


def test_diagnose_wrong_size_advice_beats_the_exposure_advice(tmp_path):
    """A master that can't be applied at all outranks "build a bias to scale it" —
    scaling a dark the engine will refuse wouldn't calibrate anything."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0, width=1080, height=1920)

    advice = calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0,
        width_px=480, height_px=320)

    assert advice is not None
    assert "master bias" not in advice
    assert "binning" in advice


def test_diagnose_wrong_size_needs_every_master_to_conflict(tmp_path):
    """With one usable dark left, the size isn't why the stack was uncalibrated —
    fall through to the exposure signature (or to the generic copy)."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0, width=1080, height=1920)
    _register(root, "dark", exposure_s=30.0, gain=80.0, width=480, height=320)

    advice = calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0,
        width_px=480, height_px=320)

    assert advice is not None
    assert "binning" not in advice
    assert "master bias" in advice  # the pre-existing exposure signature


def test_diagnose_wrong_size_is_silent_without_known_dimensions(tmp_path):
    """Unchanged behaviour when the size can't be judged: an older master that
    never recorded its dimensions, or a target whose frames didn't either."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=10.0, gain=80.0, width=1080, height=1920)
    masters = calibration.list_masters(root)

    # The target's frames never recorded a size.
    assert calibration.diagnose_uncalibrated(
        masters, exposure_s=10.0, gain=80.0,
        width_px=None, height_px=None) is None
    # …and neither did the master.
    for m in masters:
        m["width_px"] = m["height_px"] = None
    assert calibration.diagnose_uncalibrated(
        masters, exposure_s=10.0, gain=80.0,
        width_px=480, height_px=320) is None


def test_diagnose_flags_wrong_camera_flats_in_the_plural(tmp_path):
    """Several flats, none of which fit — say so once, without naming a size that
    is only one of several."""
    root = tmp_path / "lib"
    _register(root, "flat", exposure_s=2.0, gain=80.0, width=1080, height=1920)
    _register(root, "flat", exposure_s=3.0, gain=80.0, width=2080, height=3840)

    advice = calibration.diagnose_uncalibrated(
        calibration.list_masters(root), exposure_s=10.0, gain=80.0,
        width_px=480, height_px=320)

    assert advice is not None
    assert "None of your master flats" in advice
    assert "480×320" in advice


def test_bayer_conflict_only_refuses_a_provable_mismatch():
    """The colour-filter twin of the size rule: one-sided, so nothing that binds
    today stops binding. Only a flat is ever gated on it (a dark/bias corrects
    each physical pixel), but the predicate itself is kind-agnostic."""
    grbg = {"bayer_pattern": "GRBG"}
    assert calibration.bayer_conflict(grbg, "RGGB") is True
    assert calibration.bayer_conflict(grbg, "grbg ") is False  # header noise
    assert calibration.bayer_conflict(grbg, None) is False
    assert calibration.bayer_conflict(grbg, "MONO") is False   # not a CFA phase
    assert calibration.bayer_conflict({}, "RGGB") is False
    assert calibration.bayer_conflict({"bayer_pattern": ""}, "RGGB") is False


def test_modal_bayer_votes_only_on_real_cfa_phases():
    assert calibration.modal_bayer(["RGGB", "rggb", "GRBG"]) == "RGGB"
    assert calibration.modal_bayer(["", None, "MONO"]) is None
    assert calibration.modal_bayer([]) is None


def test_auto_bind_skips_a_bayer_mismatched_flat_but_keeps_the_dark(tmp_path):
    """A flat from a sensor with a different Bayer phase must NOT be auto-bound:
    the engine refuses it (it would divide red photosites by a green correction
    and tint every frame), so binding it would abort the walk-away stack — the
    same reasoning as the dimension gate. The *dark* on that phase still binds,
    because a pedestal corrects each physical pixel."""
    root = tmp_path / "lib"
    dark = _register(root, "dark", exposure_s=30.0, gain=80.0, bayer_pattern="GRBG")
    _register(root, "flat", exposure_s=2.0, gain=80.0, bayer_pattern="GRBG")

    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root),
        exposure_s=30.0, gain=80.0, bayer_pattern="RGGB")
    assert Path(bound["dark_path"]).name == dark["filename"]
    assert "flat_path" not in bound

    # A further-but-matching flat binds rather than being masked by the refused
    # one — the same "don't let an unbindable top pick hide a bindable one" rule
    # the dimension gate already follows.
    same = _register(root, "flat", exposure_s=2.0, gain=80.0, bayer_pattern="RGGB")
    bound2 = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root),
        exposure_s=30.0, gain=80.0, bayer_pattern="RGGB")
    assert Path(bound2["flat_path"]).name == same["filename"]


def test_auto_bind_bayer_gate_is_inert_without_both_sides(tmp_path):
    """Every master the owner already has predates the ``BAYERPAT`` stamp, and a
    caller that passes no phase is the old signature — both must bind exactly as
    before."""
    root = tmp_path / "lib"
    legacy = _register(root, "flat", exposure_s=2.0, gain=80.0)  # no BAYERPAT
    bound = calibration.auto_bind_master_paths(
        root, calibration.list_masters(root),
        exposure_s=30.0, gain=80.0, bayer_pattern="RGGB")
    assert Path(bound["flat_path"]).name == legacy["filename"]

    root2 = tmp_path / "lib2"
    stamped = _register(root2, "flat", exposure_s=2.0, gain=80.0,
                        bayer_pattern="GRBG")
    bound2 = calibration.auto_bind_master_paths(
        root2, calibration.list_masters(root2), exposure_s=30.0, gain=80.0)
    assert Path(bound2["flat_path"]).name == stamped["filename"]


def test_coverage_miss_reason_names_the_bayer_phase(tmp_path):
    """The "why doesn't this master cover that target?" clause must name the real
    blocker, not fall through to "another master is a closer match"."""
    reason = calibration.coverage_miss_reason(
        {"kind": "flat", "bayer_pattern": "GRBG", "width_px": 4, "height_px": 4,
         "exists": True},
        exposure_s=30.0, gain=80.0, width_px=4, height_px=4,
        bayer_pattern="RGGB")
    assert reason is not None and "GRBG" in reason and "RGGB" in reason
    # A dark on that same phase is not blocked by it.
    assert calibration.coverage_miss_reason(
        {"kind": "dark", "bayer_pattern": "GRBG", "width_px": 4, "height_px": 4,
         "exists": True, "exposure_s": 30.0},
        exposure_s=30.0, gain=80.0, width_px=4, height_px=4,
        bayer_pattern="RGGB") is None


def test_dims_conflict_only_refuses_a_provable_mismatch():
    """The one shared rule every size gate uses, so the binders and the diagnosis
    can never disagree about which masters fit."""
    fits = {"width_px": 480, "height_px": 320}
    assert calibration.dims_conflict(fits, 480, 320) is False
    assert calibration.dims_conflict(fits, 1080, 1920) is True
    assert calibration.dims_conflict(fits, None, 320) is False
    assert calibration.dims_conflict({"width_px": None, "height_px": None},
                                     480, 320) is False
    assert calibration.dims_conflict({"width_px": "?", "height_px": "?"},
                                     480, 320) is False


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


def test_calibration_suggestions_reports_the_targets_frame_size(client, solved_library):
    """The Stack form needs the subs' size to warn that a master built for another
    camera/binning can't be applied — the engine refuses it and fails the whole
    stack, so an advisory after the fact is too late."""
    from tests.webapp.conftest import FRAME_H, FRAME_W

    safe = client.get("/api/targets").json()[0]["safe_name"]
    body = client.get(f"/api/targets/{safe}/calibration-suggestions").json()

    assert body["params"]["width_px"] == FRAME_W
    assert body["params"]["height_px"] == FRAME_H


def test_calibration_suggestions_serves_the_engines_own_mismatch_tolerances(
        client, solved_library):
    """The Stack form warns about the same exposure/temperature mismatches the
    finished run reports. Each side used to pick its own threshold, so on a
    borderline pair (a 30 s dark on 25 s subs) the app stayed quiet before the
    night was spent and complained afterwards. The endpoint now serves the
    engine's constants — and this pins that they *are* the engine's, so changing
    ``calibration_warnings``' sensitivity can't silently leave the form behind."""
    from seestack.calibrate.apply import EXPOSURE_MISMATCH_TOL, TEMP_MISMATCH_TOL_C

    safe = client.get("/api/targets").json()[0]["safe_name"]
    tol = client.get(f"/api/targets/{safe}/calibration-suggestions").json()["tolerances"]

    assert tol["exposure_frac"] == EXPOSURE_MISMATCH_TOL
    assert tol["temp_c"] == TEMP_MISMATCH_TOL_C
    # The pair the form used to let through is on the warning side of the served
    # threshold, measured the way the engine measures it (against the master).
    assert abs(25.0 / 30.0 - 1.0) > tol["exposure_frac"]


def test_calibration_suggestions_frame_size_is_none_when_unrecorded(
        client, solved_library):
    """A target whose frames never recorded a size reports None rather than
    guessing — the form then can't disprove any master, so it flags none."""
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, width_px=None, height_px=None)
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/calibration-suggestions").json()

    assert body["params"]["width_px"] is None
    assert body["params"]["height_px"] is None


def test_modal_dim_ignores_strays_and_unknowns():
    """The *modal* size, so one mis-ingested frame from another camera doesn't
    move the size every master is judged against."""
    assert calibration.modal_dim([1080, 1080, 1080, 540]) == 1080
    assert calibration.modal_dim([None, 1080, "bad", 1080]) == 1080
    assert calibration.modal_dim([]) is None
    assert calibration.modal_dim([None, None]) is None


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


def test_build_master_cancel_is_classified_cancelled(client, data_root, tmp_path, monkeypatch):
    """Cancelling a Build-master job stops it and marks the job 'cancelled' (not a
    misleading 'done'), and no master is registered. A dark/flat set can be many
    frames, so the build must honour the Jobs-page Cancel button."""
    import threading

    from seestack.calibrate import masters as masters_mod

    darks = tmp_path / "darks"
    _write_darks(darks, n=8)

    started = threading.Event()

    def blocking_build_master(*args, should_stop=None, **kwargs):
        # Stand in for a long build: block until the test asks to cancel, then
        # honour it exactly like the real per-frame checkpoint (return None).
        started.set()
        while not (should_stop is not None and should_stop()):
            time.sleep(0.01)
        return None

    monkeypatch.setattr(masters_mod, "build_master", blocking_build_master)

    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": str(darks)})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    assert started.wait(10), "build never started"
    c = client.post(f"/api/jobs/{job_id}/cancel")
    assert c.status_code == 200, c.text

    job = _wait_job(client, job_id)
    assert job["state"] == "cancelled", job
    # No partial master was written to the store.
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


# --- "Do my masters actually cover my targets?" -----------------------------
#
# The Calibration page lists the masters you've built but never connects them
# back to the library, so a beginner discovers a gap target-by-target (on the
# Stack form, or after an uncalibrated result). ``master_coverage`` answers it
# once, using the *unattended binder's* own confidence gate so the roll-up
# promises exactly what the app will do on its own.


def _coverage_master(root: Path, kind: str, *, name: str, exposure_s=10.0,
                     gain=80.0, width=480, height=320, temp=-10.0) -> dict:
    from seestack.calibrate.masters import MasterMeta

    arr = np.full((height, width), 7.0, dtype=np.float32)
    meta = MasterMeta(kind, 5, width, height, "median", exposure_s=exposure_s,
                      gain=gain, sensor_temp_c=temp)
    return calibration.register_master(root, name=name, array=arr, meta=meta)


def _coverage_target(name: str, *, exposure_s=10.0, gain=80.0, temp=-10.0,
                     width=480, height=320) -> dict:
    return {"name": name, "safe_name": name.replace(" ", "_"),
            "exposure_s": exposure_s, "gain": gain, "sensor_temp_c": temp,
            "width_px": width, "height_px": height}


def test_master_coverage_counts_the_targets_a_master_reaches(tmp_path):
    """The headline number: one 10 s dark covers the two 10 s targets and misses
    the 60 s one — the answer the page currently makes you work out per target."""
    root = tmp_path / "library"
    dark = _coverage_master(root, "dark", name="10s dark", exposure_s=10.0)
    masters = calibration.list_masters(root)

    cov = calibration.master_coverage(root, masters, [
        _coverage_target("M 42"),
        _coverage_target("NGC 7000"),
        _coverage_target("Long Sub", exposure_s=60.0),
    ])

    assert cov["n_targets"] == 3
    row = next(r for r in cov["masters"] if r["id"] == dark["id"])
    assert row["kind"] == "dark"
    assert row["n_covered"] == 2
    assert row["covered"] == ["M 42", "NGC 7000"]
    assert row["missed"] == ["Long Sub"]  # 6× the exposure, no bias to scale with
    assert cov["uncovered"] == ["Long Sub"]


def test_master_coverage_flags_a_target_no_master_reaches(tmp_path):
    """A second camera (or a binning change) is the case a beginner never sees
    coming: the master looks fine on the page but fits none of those subs."""
    root = tmp_path / "library"
    _coverage_master(root, "dark", name="S50 dark", width=1080, height=1920)
    masters = calibration.list_masters(root)

    cov = calibration.master_coverage(
        root, masters, [_coverage_target("M 13", width=480, height=320)])

    assert cov["masters"][0]["n_covered"] == 0
    assert cov["uncovered"] == ["M 13"]


def test_master_coverage_with_no_masters_reports_every_target_uncovered(tmp_path):
    """The empty-library case: no rows, and every target is honestly uncovered."""
    root = tmp_path / "library"

    cov = calibration.master_coverage(root, [], [
        _coverage_target("M 42"), _coverage_target("M 31")])

    assert cov["masters"] == []
    assert cov["uncovered"] == ["M 42", "M 31"]
    assert cov["n_targets"] == 2


def test_master_coverage_with_no_targets_is_empty_not_an_error(tmp_path):
    """A fresh install has masters and no targets — the roll-up must still answer
    (every master covers nothing) rather than divide by zero."""
    root = tmp_path / "library"
    _coverage_master(root, "flat", name="Flat", exposure_s=None)
    masters = calibration.list_masters(root)

    cov = calibration.master_coverage(root, masters, [])

    assert cov["n_targets"] == 0
    assert cov["uncovered"] == []
    assert cov["masters"][0]["n_covered"] == 0
    assert cov["masters"][0]["missed"] == []


# --- ...and *why* each miss misses ------------------------------------------
#
# The roll-up above is the diagnosis ("this dark reaches 2 of your 3 targets");
# the cure was still "go read the build form and work out what numbers to use".
# ``coverage_miss_reason`` names the blocker the gates already know about, so the
# list becomes something a beginner can act on.


def test_miss_reason_names_the_exposure_gap_for_a_dark(tmp_path):
    """The commonest beginner miss: one dark, subs shot at another exposure. The
    clause must carry *both* numbers and the fix (a bias lets us scale it)."""
    root = tmp_path / "library"
    _coverage_master(root, "dark", name="30s dark", exposure_s=30.0)
    master = calibration.list_masters(root)[0]

    reason = calibration.coverage_miss_reason(
        master, exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
        width_px=480, height_px=320)

    assert reason is not None
    assert "10s" in reason and "30s" in reason
    assert "master bias" in reason


def test_miss_reason_names_a_frame_size_conflict_first(tmp_path):
    """A second camera/binning is decisive — it must win over any other clause,
    and name both sizes so the user can tell which scope it came from."""
    root = tmp_path / "library"
    _coverage_master(root, "dark", name="S50 dark", width=1080, height=1920,
                     exposure_s=30.0, gain=200.0)
    master = calibration.list_masters(root)[0]

    reason = calibration.coverage_miss_reason(
        master, exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
        width_px=480, height_px=320)

    assert reason is not None
    assert "1080×1920" in reason and "480×320" in reason
    assert "camera or binning" in reason


def test_miss_reason_names_the_gain_for_a_flat(tmp_path):
    """A flat is exposure-independent, so the only thing that can disqualify it
    (size aside) is the rig it was shot on — say which gain."""
    root = tmp_path / "library"
    _coverage_master(root, "flat", name="Flat", exposure_s=2.0, gain=400.0)
    master = calibration.list_masters(root)[0]

    reason = calibration.coverage_miss_reason(
        master, exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
        width_px=480, height_px=320)

    assert reason is not None
    assert "gain 400" in reason and "gain 80" in reason


def test_miss_reason_is_none_when_the_master_itself_fits(tmp_path):
    """`None` is the "nothing wrong with this master" signal the caller needs, so
    it can say "another master won" instead of inventing a defect."""
    root = tmp_path / "library"
    _coverage_master(root, "dark", name="10s dark", exposure_s=10.0)
    master = calibration.list_masters(root)[0]

    assert calibration.coverage_miss_reason(
        master, exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
        width_px=480, height_px=320) is None


def test_master_coverage_explains_every_miss(tmp_path):
    """End-to-end through the roll-up: each missed target carries its own reason,
    in the same order as the bare `missed` list it explains."""
    root = tmp_path / "library"
    dark = _coverage_master(root, "dark", name="10s dark", exposure_s=10.0)
    masters = calibration.list_masters(root)

    cov = calibration.master_coverage(root, masters, [
        _coverage_target("M 42"),
        _coverage_target("Long Sub", exposure_s=60.0),
        _coverage_target("Other Cam", width=1080, height=1920),
    ])

    row = next(r for r in cov["masters"] if r["id"] == dark["id"])
    assert row["missed"] == ["Long Sub", "Other Cam"]
    assert [d["name"] for d in row["missed_detail"]] == ["Long Sub", "Other Cam"]
    assert "60s" in row["missed_detail"][0]["reason"]
    assert "camera or binning" in row["missed_detail"][1]["reason"]


def test_master_coverage_says_a_bias_was_passed_over_for_a_dark(tmp_path):
    """A bias that fits perfectly is still "missed" whenever a dark was bound —
    a dark already carries the bias. Blaming the bias would be a lie."""
    root = tmp_path / "library"
    _coverage_master(root, "dark", name="10s dark", exposure_s=10.0)
    bias = _coverage_master(root, "bias", name="Bias", exposure_s=0.0)
    masters = calibration.list_masters(root)

    cov = calibration.master_coverage(root, masters, [_coverage_target("M 42")])

    row = next(r for r in cov["masters"] if r["id"] == bias["id"])
    assert row["missed"] == ["M 42"]
    assert "a dark already includes the bias" in row["missed_detail"][0]["reason"]


def test_master_coverage_reports_what_an_uncovered_target_was_shot_at(tmp_path):
    """"Build a dark from frames shot the same way" is only actionable if you know
    *which* way — so the roll-up carries each uncovered target's own numbers."""
    root = tmp_path / "library"

    cov = calibration.master_coverage(root, [], [
        _coverage_target("M 42", exposure_s=10.0, gain=80.0),
        _coverage_target("Long Sub", exposure_s=60.0, gain=200.0),
    ])

    assert cov["uncovered"] == ["M 42", "Long Sub"]
    assert cov["uncovered_detail"] == [
        {"name": "M 42", "exposure_s": 10.0, "gain": 80.0},
        {"name": "Long Sub", "exposure_s": 60.0, "gain": 200.0},
    ]


def test_calibration_coverage_endpoint_serves_the_miss_reasons(
        client, solved_library, tmp_path):
    """The reasons must survive the endpoint (they're what the tooltip shows)."""
    root = solved_library / "library"
    # The fixture's subs are 10 s; this dark is 30 s, so it reaches neither.
    dark = _coverage_master(root, "dark", name="30s dark", exposure_s=30.0)

    body = client.get("/api/calibration/coverage").json()

    row = next(r for r in body["masters"] if r["id"] == dark["id"])
    assert row["n_covered"] == 0
    assert len(row["missed_detail"]) == len(row["missed"]) == 2
    assert all("30s" in d["reason"] for d in row["missed_detail"])


def test_calibration_coverage_endpoint_reports_the_librarys_targets(
        client, solved_library, tmp_path):
    """End-to-end: the endpoint reads each target's own frames and reports a
    master built to match them as covering both fixture targets."""
    root = solved_library / "library"
    # The fixture's subs are 480×320 raw, 10 s at gain 80, −10 °C.
    dark = _coverage_master(root, "dark", name="Matching dark")

    body = client.get("/api/calibration/coverage").json()

    assert body["n_targets"] == 2
    row = next(r for r in body["masters"] if r["id"] == dark["id"])
    assert row["n_covered"] == 2
    assert sorted(row["covered"]) == ["M_42", "NGC_7000"]
    assert body["uncovered"] == []
    # Auto-calibration is off by default, so the page must not promise hands-off
    # use — a covered master still has to be picked on the Stack form.
    assert body["auto_apply"] is False


def test_calibration_coverage_endpoint_with_no_masters(client):
    """A library with no masters yet — a plain, honest empty answer, not a 500,
    with every target it does know about reported as covered by nothing."""
    body = client.get("/api/calibration/coverage").json()
    assert body["masters"] == []
    assert len(body["uncovered"]) == body["n_targets"]


# --- The confident binding, served to the Stack form as ids -------------------
#
# `recommend_masters` answers "the best master of each kind you own"; the
# unattended binder answers the stricter "the best one we're confident about".
# The two can disagree, and until the form could read the second, a watched stack
# and a walk-away stack of the same subs were calibrated differently.


def test_bound_ids_and_bound_paths_are_one_decision(tmp_path):
    """Pinned by construction, not by a literal: whatever the confidence gates
    do, the ids the form reads must resolve to exactly the paths the unattended
    stack binds — otherwise the two answers can drift apart again."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=30.0, gain=80.0)
    _register(root, "flat", exposure_s=2.0, gain=80.0)
    _register(root, "bias", exposure_s=0.0, gain=80.0)
    masters = calibration.list_masters(root)

    kw = dict(exposure_s=30.0, gain=80.0)
    ids = calibration.auto_bind_master_ids(root, masters, **kw)
    paths = calibration.auto_bind_master_paths(root, masters, **kw)

    assert ids, "the fixture should bind something, or this proves nothing"
    for id_key, path_key in calibration._BOUND_ID_TO_PATH_KEY.items():
        if id_key in ids:
            assert str(calibration.master_path(root, ids[id_key])) == paths[path_key]
        else:
            assert path_key not in paths
    assert ids.get("scale_dark_to_light") == paths.get("scale_dark_to_light")


def test_bound_ids_carry_the_scaling_pair(tmp_path):
    """A dark recovered by exposure-scaling is only correct *with* its bias and
    the switch, so the id form has to carry all three."""
    root = tmp_path / "lib"
    dark = _register(root, "dark", exposure_s=30.0, gain=80.0)
    bias = _register(root, "bias", exposure_s=0.0, gain=80.0)

    ids = calibration.auto_bind_master_ids(
        root, calibration.list_masters(root), exposure_s=10.0, gain=80.0)
    assert ids["dark_master_id"] == dark["id"]
    assert ids["bias_master_id"] == bias["id"]
    assert ids["scale_dark_to_light"] is True


def test_bound_ids_are_empty_when_nothing_is_confident(tmp_path):
    """"Nothing confident" must be sayable — the form falls back to its
    best-available recommendation there, which is right with a human watching."""
    root = tmp_path / "lib"
    _register(root, "dark", exposure_s=300.0, gain=400.0)  # wrong gain and exposure
    assert calibration.auto_bind_master_ids(
        root, calibration.list_masters(root), exposure_s=30.0, gain=80.0) == {}


def test_suggestions_serve_what_the_unattended_stack_would_bind(
        client, solved_library, data_root):
    """The Stack form's endpoint carries the confident binding beside the
    best-available one, so the form can land where a walk-away stack would."""
    root = data_root / "library"
    # Build the dark against what the endpoint says the subs actually are, so
    # the fixture can't drift from the synthetic frames' own header values.
    params = client.get("/api/targets/M_42/calibration-suggestions").json()["params"]
    dark = _register(root, "dark", exposure_s=params["exposure_s"],
                     gain=params["gain"], width=params["width_px"],
                     height=params["height_px"])
    body = client.get("/api/targets/M_42/calibration-suggestions").json()
    assert body["confident"]["dark_master_id"] == dark["id"]
    # …and it agrees with the binder itself, rather than being re-derived here.
    assert body["confident"] == calibration.auto_bind_master_ids(
        root, calibration.list_masters(root),
        exposure_s=body["params"]["exposure_s"], gain=body["params"]["gain"],
        sensor_temp_c=body["params"]["sensor_temp_c"],
        width_px=body["params"]["width_px"], height_px=body["params"]["height_px"])


def test_suggestions_confident_is_empty_when_no_master_matches(
        client, solved_library, data_root):
    """A library whose only dark is for another camera: the best-available
    recommendation still names it (the form warns), the confident binding says
    nothing at all."""
    root = data_root / "library"
    params = client.get("/api/targets/M_42/calibration-suggestions").json()["params"]
    dark = _register(root, "dark", exposure_s=params["exposure_s"],
                     gain=params["gain"], width=8, height=8)  # another camera
    body = client.get("/api/targets/M_42/calibration-suggestions").json()
    assert body["dark_master_id"] == dark["id"]
    assert body["confident"] == {}
