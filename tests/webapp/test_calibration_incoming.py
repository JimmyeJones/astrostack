"""The "we found calibration frames in your incoming folder" offer.

End-to-end over the real endpoints: discovery, the "you already have one of
these" flag, and the one-click build that resolves the folder server-side from
its id (no filesystem path ever comes from the client).
"""

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


def _write_frames(folder: Path, n: int, *, imagetyp: str | None,
                  exposure_s: float = 30.0, gain: float = 80.0,
                  temp_c: float = -5.0, shape=(8, 8)) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        hdu = fits.PrimaryHDU(data=np.full(shape, 100.0, dtype=np.float32))
        hdu.header["EXPTIME"] = exposure_s
        hdu.header["GAIN"] = gain
        hdu.header["CCD-TEMP"] = temp_c
        hdu.header["BAYERPAT"] = "RGGB"
        if imagetyp is not None:
            hdu.header["IMAGETYP"] = imagetyp
        hdu.writeto(folder / f"f_{i:03d}.fit", overwrite=True)


def test_nothing_is_offered_for_a_library_of_lights(client, data_root):
    """The fixture's incoming folder is two targets of synthetic subs — which
    carry no ``IMAGETYP`` at all — so the offer must be empty. A feature that
    fires on an ordinary install is the failure mode, not the success one."""
    body = client.get("/api/calibration/incoming").json()

    assert body["folders"] == []
    assert body["incoming_dir"].endswith("incoming")


def test_a_declared_dark_folder_is_offered_with_a_name_you_can_read(
        client, data_root):
    _write_frames(data_root / "incoming" / "Dark", 8, imagetyp="Dark Frame")

    body = client.get("/api/calibration/incoming").json()

    assert len(body["folders"]) == 1
    f = body["folders"][0]
    assert f["kind"] == "dark"
    assert f["name"] == "Dark"
    assert f["n_frames"] == 8
    assert f["suggested_name"] == "Dark 30s gain 80 −5°C"
    assert f["have_master"] is None
    # The absolute path is server-side only: the client is given an id.
    assert "folder" not in f
    assert f["id"] == "Dark"


def test_building_from_the_offer_registers_a_master_of_that_kind(
        client, data_root):
    _write_frames(data_root / "incoming" / "Dark", 6, imagetyp="Dark")
    fid = client.get("/api/calibration/incoming").json()["folders"][0]["id"]

    r = client.post(f"/api/calibration/incoming/{fid}/build")
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    masters = client.get("/api/calibration/masters").json()
    assert len(masters) == 1
    assert masters[0]["kind"] == "dark"
    assert masters[0]["n_frames"] == 6
    assert masters[0]["name"] == "Dark 30s gain 80 −5°C"
    # The frames said what they are, so the built master says so too.
    assert masters[0]["header_kinds"] == {"dark": 6}


def test_an_unknown_folder_id_is_a_404_not_a_500(client, data_root):
    r = client.post("/api/calibration/incoming/no-such-folder/build")

    assert r.status_code == 404
    assert "no longer" in r.json()["detail"]


def test_the_offer_says_when_you_already_have_that_master(client, data_root):
    """Built last week → the card says so instead of inviting a duplicate."""
    _write_frames(data_root / "incoming" / "Dark", 6, imagetyp="Dark")
    fid = client.get("/api/calibration/incoming").json()["folders"][0]["id"]
    job = _wait_job(
        client, client.post(f"/api/calibration/incoming/{fid}/build")
        .json()["job_id"])
    assert job["state"] == "done", job

    f = client.get("/api/calibration/incoming").json()["folders"][0]

    assert f["have_master"] is not None
    assert f["have_master"]["name"] == "Dark 30s gain 80 −5°C"


def test_a_master_for_a_different_exposure_does_not_count_as_covering(
        client, data_root):
    """A 30 s dark does not calibrate 10 s subs, so a 10 s dark folder is still
    worth offering — same bar the unattended binder applies."""
    _write_frames(data_root / "incoming" / "Dark30", 6, imagetyp="Dark",
                  exposure_s=30.0)
    _write_frames(data_root / "incoming" / "Dark10", 6, imagetyp="Dark",
                  exposure_s=10.0)
    listed = client.get("/api/calibration/incoming").json()["folders"]
    thirty = next(f for f in listed if f["name"] == "Dark30")
    job = _wait_job(
        client,
        client.post(f"/api/calibration/incoming/{thirty['id']}/build")
        .json()["job_id"])
    assert job["state"] == "done", job

    listed = client.get("/api/calibration/incoming").json()["folders"]
    by_name = {f["name"]: f for f in listed}

    assert by_name["Dark30"]["have_master"] is not None
    assert by_name["Dark10"]["have_master"] is None


def test_flats_and_biases_are_offered_too(client, data_root):
    _write_frames(data_root / "incoming" / "Flat", 6, imagetyp="Flat Field",
                  exposure_s=0.5)
    _write_frames(data_root / "incoming" / "Bias", 6, imagetyp="Bias",
                  exposure_s=0.001)

    kinds = {f["kind"] for f in
             client.get("/api/calibration/incoming").json()["folders"]}

    assert kinds == {"flat", "bias"}


def test_the_endpoint_never_writes_to_incoming(client, data_root):
    """``incoming/`` is strictly read-only (AGENTS.md §10) — the scan and the
    build must both leave every path under it byte-for-byte untouched."""
    incoming = data_root / "incoming"
    _write_frames(incoming / "Dark", 6, imagetyp="Dark")

    def snapshot():
        return {
            str(p.relative_to(incoming)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(incoming.rglob("*")) if p.is_file()
        }

    before = snapshot()
    fid = client.get("/api/calibration/incoming").json()["folders"][0]["id"]
    job = _wait_job(
        client, client.post(f"/api/calibration/incoming/{fid}/build")
        .json()["job_id"])
    assert job["state"] == "done", job

    assert snapshot() == before


def _folder(**over):
    """A discovered folder, as :mod:`seestack.calibrate.discover` returns one."""
    from seestack.calibrate.discover import CalibrationFolder

    base = dict(
        id="Dark", folder_name="Dark", rel_path="Dark", folder="/i/Dark",
        kind="dark", declared={"dark": 4}, n_frames=40, n_sampled=4,
        exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
        width_px=480, height_px=320,
    )
    base.update(over)
    return CalibrationFolder(**base)


SUBS = dict(exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0,
            width_px=480, height_px=320)


def test_incoming_advice_names_the_frames_you_already_have():
    advice = calibration.incoming_calibration_advice([_folder()], [], **SUBS)

    assert advice is not None
    assert "40 dark frames" in advice
    assert "“Dark”" in advice
    assert "Calibration page" in advice


def test_incoming_advice_stays_quiet_when_the_folder_would_not_cover_these_subs():
    """A 30 s dark folder is no use to 10 s subs — the same bar the unattended
    binder applies, so the advice can't send anyone off on a useless build."""
    assert calibration.incoming_calibration_advice(
        [_folder(exposure_s=30.0)], [], **SUBS) is None
    # ...nor a folder from a different camera.
    assert calibration.incoming_calibration_advice(
        [_folder(width_px=1080, height_px=1920)], [], **SUBS) is None


def test_incoming_advice_stays_quiet_when_you_already_built_that_master():
    """Then the stack is uncalibrated for some other reason, and pointing at a
    build they have already done would be worse than saying nothing."""
    built = {"id": 1, "name": "Dark 10s", "kind": "dark", "exists": True,
             "exposure_s": 10.0, "gain": 80.0, "sensor_temp_c": -10.0,
             "width_px": 480, "height_px": 320}

    assert calibration.incoming_calibration_advice(
        [_folder()], [built], **SUBS) is None


def test_incoming_advice_names_the_dark_first():
    """A dark is what an uncalibrated Seestar stack is actually short of."""
    flat = _folder(id="Flat", folder_name="Flat", rel_path="Flat", kind="flat",
                   declared={"flat": 4}, exposure_s=0.5)
    advice = calibration.incoming_calibration_advice(
        [flat, _folder()], [], **SUBS)

    assert advice is not None and "dark frames" in advice


def test_incoming_advice_is_empty_with_nothing_found():
    assert calibration.incoming_calibration_advice([], [], **SUBS) is None


def test_the_uncalibrated_stack_says_you_already_have_darks(
        client, solved_library):
    """End to end: an uncalibrated run's info payload points at the frames in
    ``incoming/`` instead of the generic "go build a master" copy."""
    import numpy as np

    from .conftest import FRAME_H, FRAME_W
    from .test_stack_render import _make_run_with_fits

    darks = solved_library / "incoming" / "MyDarks"
    darks.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        hdu = fits.PrimaryHDU(
            data=np.full((FRAME_H, FRAME_W), 100, dtype=np.uint16))
        hdu.header["IMAGETYP"] = "Dark Frame"
        hdu.header["EXPTIME"] = 10.0
        hdu.header["GAIN"] = 80.0
        hdu.header["CCD-TEMP"] = -10.0
        hdu.writeto(darks / f"d_{i}.fit", overwrite=True)

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    # Advice is only derived for a run that carries provenance but no CALSTAT —
    # i.e. one that was stacked and came out uncalibrated.
    from seestack.io.library import Library

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()

    assert body["calibration_advice"] is not None
    assert "6 dark frames" in body["calibration_advice"]
    assert "MyDarks" in body["calibration_advice"]


def test_existing_master_like_is_one_sided_about_unknowns():
    """A master that never recorded its gain/temperature can't be *disproved*,
    so it still counts as covering — the same asymmetry every other gate in this
    module uses."""
    bare = {"id": 1, "name": "Dark", "kind": "dark", "exists": True,
            "exposure_s": None, "gain": None, "sensor_temp_c": None,
            "width_px": None, "height_px": None}

    assert calibration.existing_master_like(
        [bare], kind="dark", exposure_s=30.0, gain=80.0, sensor_temp_c=-5.0,
    ) is bare
    # ...but a provably different sensor size is a disproof.
    sized = {**bare, "width_px": 100, "height_px": 100}
    assert calibration.existing_master_like(
        [sized], kind="dark", exposure_s=30.0, gain=80.0, sensor_temp_c=-5.0,
        width_px=200, height_px=200,
    ) is None
    # ...and a master of another kind never covers this one.
    assert calibration.existing_master_like(
        [bare], kind="flat", exposure_s=None, gain=80.0, sensor_temp_c=-5.0,
    ) is None


def test_the_one_click_build_leaves_out_lights_the_sampling_missed(
        client, data_root):
    """The gap the sampled classification leaves open, end to end.

    ``classify_folder`` confirms a folder's kind from only
    ``discover.SAMPLE_HEADERS`` (4) evenly-spaced headers, so a folder holding ten
    darks *and* two lights whose sampled positions all read "dark" is offered as a
    dark folder. The build must not then combine the lights: a contaminated master
    dark is subtracted from every frame it is later applied to.

    Twelve files ⇒ the sampler reads indices 0/4/7/11, so the lights at 5 and 6 are
    exactly the ones it cannot see.
    """
    folder = data_root / "incoming" / "Dark"
    _write_frames(folder, 12, imagetyp="Dark Frame")
    for i in (5, 6):
        hdu = fits.PrimaryHDU(data=np.full((8, 8), 9000.0, dtype=np.float32))
        hdu.header["EXPTIME"] = 30.0
        hdu.header["GAIN"] = 80.0
        hdu.header["CCD-TEMP"] = -5.0
        hdu.header["BAYERPAT"] = "RGGB"
        hdu.header["IMAGETYP"] = "Light Frame"
        hdu.writeto(folder / f"f_{i:03d}.fit", overwrite=True)

    offered = client.get("/api/calibration/incoming").json()["folders"]
    assert len(offered) == 1 and offered[0]["kind"] == "dark"

    r = client.post(f"/api/calibration/incoming/{offered[0]['id']}/build")
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    result = job["result"]
    assert result["n_frames"] == 10                      # not 12
    assert result["skipped_buckets"] == {"wrong kind": 2}
    # ...and the master says it is made of darks only, so the header note is silent.
    assert result["header_kinds"] == {"dark": 10}

    master = client.get("/api/calibration/masters").json()[0]
    assert master["n_frames"] == 10
    # The registered master is the darks' own level (100), not a mean dragged up
    # by two 9000-count lights — which over 12 frames would have landed near 1580.
    from seestack.calibrate import load_master

    array, _meta = load_master(
        calibration.master_path(data_root / "library", master["id"]))
    assert float(np.nanmean(array)) == 100.0


def test_a_manual_build_still_takes_the_folder_as_given(client, data_root):
    """The filter is scoped to the *discovered* offer. ``build_master``'s own
    default is unchanged, so a build the user aimed at a folder themselves keeps
    combining what is in it — the behaviour the header note exists to explain."""
    from seestack.calibrate.masters import build_master

    folder = data_root / "incoming" / "Mixed"
    _write_frames(folder, 4, imagetyp="Dark Frame")
    _write_frames(folder / "extra", 2, imagetyp="Light Frame")
    paths = sorted(folder.glob("*.fit")) + sorted((folder / "extra").glob("*.fit"))

    _master, meta = build_master(paths, kind="dark", method="mean")

    assert meta.n_frames == 6
    assert meta.header_kinds == {"dark": 4, "light": 2}
