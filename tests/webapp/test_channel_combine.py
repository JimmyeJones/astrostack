"""End-to-end channel combine: stack two targets mono, then combine to RGB."""

from __future__ import annotations

import time


def _wait_job(client, job_id, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _mono_stack(client, safe):
    r = client.post(f"/api/targets/{safe}/stack", json={
        "mono": True, "sigma_clip": False, "background_flatten": False,
        "suppress_hot_pixels": False, "max_workers": 2,
    })
    assert r.status_code == 200, r.text
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"
    return client.get(f"/api/targets/{safe}/stack-runs").json()[0]["id"]


def test_channel_combine_end_to_end(client, solved_library):
    # Two mono stacks on the same target's frames stand in for two filters; both
    # share M_42's canvas so they combine cleanly.
    rid = _mono_stack(client, "M_42")

    r = client.post("/api/targets/M_42/channel-combine", json={
        "output_name": "rgb_test",
        "items": [
            {"safe": "M_42", "run_id": rid, "channel": "R"},
            {"safe": "M_42", "run_id": rid, "channel": "G"},
            {"safe": "M_42", "run_id": rid, "channel": "B"},
        ],
    })
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert set(job["result"]["channels"]) == {"R", "G", "B"}

    runs = client.get("/api/targets/M_42/stack-runs").json()
    combined = next(run for run in runs if run["output_basename"] == "rgb_test")

    # The combined FITS should carry provenance metadata (how it was made).
    import io

    from astropy.io import fits
    r = client.get(f"/api/targets/M_42/stack-runs/{combined['id']}/fits")
    assert r.status_code == 200
    header = fits.getheader(io.BytesIO(r.content))
    assert header["NCOMBINE"] == 3
    assert header["STACKMTD"] == "channel-combine (RGB)"


def test_channel_combine_requires_items(client, solved_library):
    r = client.post("/api/targets/M_42/channel-combine", json={"items": []})
    assert r.status_code == 400


def test_channel_combine_bad_channel(client, solved_library):
    rid = _mono_stack(client, "M_42")
    r = client.post("/api/targets/M_42/channel-combine", json={
        "items": [{"safe": "M_42", "run_id": rid, "channel": "Z"}],
    })
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "error"
