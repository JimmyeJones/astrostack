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
