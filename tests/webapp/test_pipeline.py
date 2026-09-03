"""End-to-end pipeline via the API: scan → QC/solve, then stack.

ASTAP is not installed in CI, so solve gracefully marks frames unsolved; QC
still runs and the pipeline completes. The stack test is skipped if the
optional ``reproject`` dependency isn't present.
"""

from __future__ import annotations

import time
from pathlib import Path


def _build_mixed_pointing_target(data_root: Path, *, n_each: int = 6) -> None:
    """One incoming folder → one target whose solved frames form TWO well-separated
    pointings (a batch that looks like two objects dropped in one folder)."""
    from synth import make_synth_wcs_text, write_seestar_fits

    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    incoming = data_root / "incoming"
    d = incoming / "M_MIXED"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(2 * n_each):
        write_seestar_fits(
            d / f"frame_{i:03d}.fit", n_stars=30, seed=200 + i,
            add_wcs=True, ra_center_deg=83.6, dec_center_deg=-5.0,
        )

    lib = Library.open_or_create(data_root / "library")
    try:
        scan_and_organize(lib, incoming, copy_to_cache=False)
        proj = lib.open_target("M_MIXED")
        try:
            frames = list(proj.iter_frames())
            for idx, f in enumerate(frames):
                # First half → pointing A (RA 83.6), second half → pointing B
                # (RA 200) — ~110° apart, clearly two targets, wrap-safe geometry.
                ra = 83.6 if idx < len(frames) // 2 else 200.0
                proj.update_frame(
                    f.id, wcs_json=make_synth_wcs_text(ra_center_deg=ra),
                    ra_center_deg=ra, dec_center_deg=-5.0,
                    width_px=480, height_px=320, bayer_pattern="RGGB",
                )
        finally:
            proj.close()
        lib.refresh_target_stats("M_MIXED")
    finally:
        lib.close()


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_scan_pipeline_populates_qc(client, data_root):
    # Fresh data_root (not the built_library fixture) so scan does the ingest.
    r = client.post("/api/scan", json={})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    body = _wait_job(client, job_id)
    assert body["state"] == "done", body

    targets = client.get("/api/targets").json()
    names = {t["safe_name"] for t in targets}
    assert {"M_42", "NGC_7000"} <= names

    frames = client.get("/api/targets/M_42/frames").json()
    assert len(frames) == 3
    # QC ran → at least one frame has FWHM / star_count populated.
    assert any(f["fwhm_px"] is not None for f in frames)
    assert any(f["star_count"] is not None for f in frames)


def test_qc_solve_single_target(client, built_library):
    r = client.post("/api/targets/M_42/qc-solve")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)


def test_stack_end_to_end(client, solved_library):
    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "test_master", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "max_workers": 2},
    )
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body

    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
    run = runs[0]
    assert run["n_frames_used"] >= 1
    # The run records the producing app version for provenance (surfaced on the
    # History card as "made with vX"). The webapp passes its own __version__.
    from webapp import __version__ as app_version
    assert run["engine_version"] == app_version
    # Download the preview PNG.
    rid = run["id"]
    if run["has_preview"]:
        pr = client.get(f"/api/targets/M_42/stack-runs/{rid}/preview")
        assert pr.status_code == 200
        assert pr.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_process_target_stacks_end_to_end(client, solved_library):
    # One-click "process this target": QC + solve, then stack — in a single job.
    # solved_library already carries a synthetic WCS, so the chained stack runs
    # even without ASTAP.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    # QC ran as part of the chain.
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)
    # And the stack step produced a real run.
    result = body["result"]
    assert result["stacked"] is True
    assert result["solved_accepted"] >= 1
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
    assert runs[0]["n_frames_used"] >= 1
    # The stack summary carries the new run's id so the finished-job UI can
    # deep-link straight to that run's editor, not just the target's History.
    assert result["stack"]["run_id"] == runs[0]["id"]


def test_process_target_chains_auto_edit(client, solved_library):
    # The one-click "process this target" chains an auto-edit onto the fresh
    # master so the result is a finished *picture*: the Auto recipe is persisted
    # as the run's editor recipe (so the editor opens edited) and the run's
    # preview thumbnail is re-rendered through it.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    result = body["result"]
    assert result["stacked"] is True
    # The auto-edit ran and applied a non-empty recipe.
    assert result.get("auto_edited", 0) >= 1

    rid = result["stack"]["run_id"]
    # The Auto recipe is saved as this run's editor recipe (the editor opens on
    # the edited image, not a flat linear master).
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    saved_ops = [o for o in recipe["ops"] if o.get("enabled", True)]
    assert len(saved_ops) == result["auto_edited"]
    # The Auto recipe always includes a tone stretch — a genuine difference from
    # a plain manual stack, which opens with an empty recipe.
    assert any(o["id"] == "tone.stretch" for o in saved_ops)

    # The run's preview thumbnail was re-rendered through the recipe and is a
    # valid PNG.
    run = next(x for x in client.get("/api/targets/M_42/stack-runs").json()
               if x["id"] == rid)
    if run["has_preview"]:
        pr = client.get(f"/api/targets/M_42/stack-runs/{rid}/preview")
        assert pr.status_code == 200
        assert pr.content[:8] == b"\x89PNG\r\n\x1a\n"

    # The History Info panel gets a plain-language "what the auto-edit did" note
    # for this silently-auto-edited run — the trust layer for a result the user
    # didn't drive. It names the ops it applied and starts with "Auto-edited:".
    info = client.get(f"/api/targets/M_42/stack-runs/{rid}/info").json()
    assert isinstance(info.get("auto_edit"), str)
    assert info["auto_edit"].startswith("Auto-edited:")
    assert "natural stretch" in info["auto_edit"]

    # The auto-edit also measures the finished picture's residual sky-background
    # colour cast and stamps it into the run's provenance, so the walk-away user
    # sees whether the hands-off Auto path landed the background neutral (and the
    # owner gets a passive real-data read on Auto's colour path). It's a full
    # verdict dict with per-channel sky medians and a named cast.
    sc = info.get("sky_cast")
    assert isinstance(sc, dict), info
    assert set(sc) >= {"r", "g", "b", "neutral", "cast", "deviation"}
    assert isinstance(sc["neutral"], bool)
    assert sc["cast"] in {
        "neutral", "red", "green", "blue", "cyan", "magenta", "yellow"}
    assert sc["deviation"] >= 0.0

    # It also records which colour-calibration (white-balance) path Auto actually
    # ran and on how many stars — so the walk-away user can tell whether their
    # image was really white-balanced (star-based, the background-neutral fallback,
    # or a no-op). Present only on this auto-edited run.
    cc = info.get("color_cal")
    assert isinstance(cc, dict), info
    assert cc["mode_used"] in {"gray_star", "gaia", "background_neutral", "none"}
    assert isinstance(cc["n_stars_used"], int)
    assert cc["n_stars_used"] >= 0

    # ...and the editor's auto-note endpoint serves that same note, so opening the
    # run in the editor (where the Process deep-link lands the user) explains the
    # recipe they didn't build — the same trust layer, on the surface they see.
    note = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/auto-note").json()
    assert note["note"] == info["auto_edit"]


def test_manual_stack_has_no_auto_edit_note(client, solved_library):
    # A plain manual stack (no auto-edit chain) leaves no auto-edit note, so the
    # Info panel only annotates runs an unattended job actually auto-edited.
    r = client.post("/api/targets/M_42/stack", json={})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    rid = client.get("/api/targets/M_42/stack-runs").json()[0]["id"]
    info = client.get(f"/api/targets/M_42/stack-runs/{rid}/info").json()
    assert info.get("auto_edit") is None
    # ...and no sky-cast or colour-cal read-out either — those are stamped only by
    # the unattended auto-edit, so a manual stack carries none of the annotations.
    assert info.get("sky_cast") is None
    assert info.get("color_cal") is None


def _run_scan(client):
    r = client.post("/api/scan", json={})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    return body


def test_auto_stack_without_auto_edit_leaves_linear_master(client, solved_library):
    # Auto-stack on, auto-edit-on-autostack OFF (the default): the unattended
    # background stack produces a flat linear master with no saved editor recipe
    # — the pre-existing behaviour is unchanged by the new opt-in.
    client.put("/api/settings",
               json={"auto_stack": True, "auto_edit_on_autostack": False})
    body = _run_scan(client)
    assert "auto_edited" not in body["result"]
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert runs, "auto-stack should have produced a run"
    rid = runs[0]["id"]
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    assert [o for o in recipe["ops"] if o.get("enabled", True)] == []


def test_auto_edit_on_autostack_finishes_the_picture(client, solved_library):
    # With the opt-in on, the fully-unattended watcher path finishes the master
    # into a picture: the Auto recipe is saved as the run's editor recipe, just
    # like the one-click Process / Reprocess chains.
    client.put("/api/settings",
               json={"auto_stack": True, "auto_edit_on_autostack": True})
    body = _run_scan(client)
    assert body["result"].get("auto_edited", 0) >= 1
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert runs
    rid = runs[0]["id"]
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    saved_ops = [o for o in recipe["ops"] if o.get("enabled", True)]
    # The Auto recipe always includes a tone stretch — a genuine finished-picture
    # recipe, not the empty recipe a plain auto-stack leaves.
    assert any(o["id"] == "tone.stretch" for o in saved_ops)


def test_auto_edited_run_matches_the_reveal_and_hides_the_stretch_suggestion(
    client, solved_library,
):
    # An in-place "Process/auto-edit" run's preview PNG is the tone-mapped Auto
    # recipe result, but its FITS stays linear (the recipe is stored separately and
    # is reversible). The invariant both parity surfaces protect is the same — never
    # put something STF-matched beside a recipe-toned picture — but they can honour
    # it differently, because only one of them has a way out:
    #
    #   * the Adjust stretch suggestion promises to "match the STF preview
    #     thumbnail", and there is no STF curve that matches a recipe result, so it
    #     still self-hides (as it does for a display-space export);
    #   * the one-sub-vs-stack reveal used to self-hide for the same reason, but the
    #     run stores the very recipe its preview shows — so since v0.301.0 the sub
    #     is put through that *same* recipe and the pairing is honest. Hiding it was
    #     never the goal; not showing a mismatched pair was.
    #
    # This goes through the *watcher* auto-stack rather than the Process button, so
    # both routes into the same auto-edit are covered.
    client.put("/api/settings",
               json={"auto_stack": True, "auto_edit_on_autostack": True})
    body = _run_scan(client)
    assert body["result"].get("auto_edited", 0) >= 1
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert runs
    rid = runs[0]["id"]

    info = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/one-sub-vs-stack").json()
    assert info["available"] is True
    assert info["matched_by"] == "recipe"
    # ...and the render really is produced, not just promised.
    assert client.get(
        f"/api/targets/M_42/stack-runs/{rid}/reference-sub").status_code == 200

    sug = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/render-suggestion").json()
    assert sug["stretch"] is None and sug["black"] is None


def test_mixed_pointing_guard_skips_a_bimodal_process(client, data_root):
    # A batch that looks like two different targets in one folder: with the
    # (opt-in) mixed-pointing guard ON, the one-click Process skips the stack with
    # a plain-language reason instead of burning the run combining one pointing and
    # silently dropping the rest. With the guard OFF (the default), the same batch
    # still stacks exactly as before — the guardrail on upgrade behaviour.
    _build_mixed_pointing_target(data_root)

    # Guard on → skip with a reason, no stack run produced.
    client.put("/api/settings", json={"mixed_pointing_guard": True})
    r = client.post("/api/targets/M_MIXED/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    result = body["result"]
    assert result["stacked"] is False
    assert result["stack_skipped_reason"] == "mixed_pointings"
    assert result["mixed_pointings"]["pointings"] == 2
    assert result["mixed_pointings"]["majority"] == 6
    assert "2 different targets" in result["mixed_pointings_message"]
    assert len(client.get("/api/targets/M_MIXED/stack-runs").json()) == 0

    # Guard off (default) → the bimodal batch stacks as before (upgrade-safe: the
    # new setting never changes behaviour unless the owner opts in).
    client.put("/api/settings", json={"mixed_pointing_guard": False})
    r = client.post("/api/targets/M_MIXED/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    assert body["result"]["stacked"] is True
    assert len(client.get("/api/targets/M_MIXED/stack-runs").json()) == 1


def test_mixed_pointing_guard_skips_watcher_auto_stack(client, data_root):
    # The same guard protects the fully-unattended watcher auto-stack: a bimodal
    # target is reported as mixed-skipped (not stacked), and — crucially — the
    # attempt marker is NOT written, so once the user rejects the odd-target
    # frames a later scan re-checks and stacks rather than the target being
    # stranded.
    _build_mixed_pointing_target(data_root)
    client.put("/api/settings",
               json={"auto_stack": True, "mixed_pointing_guard": True})
    body = _run_scan(client)
    result = body["result"]
    assert "M_MIXED" in result.get("auto_stack_mixed_skipped", [])
    assert "M_MIXED" not in result.get("auto_stacked", [])
    assert len(client.get("/api/targets/M_MIXED/stack-runs").json()) == 0
    # Turning the guard back off, a re-scan now auto-stacks the (bimodal) target —
    # proof the skip didn't strand it via the crash-loop attempt marker.
    client.put("/api/settings",
               json={"auto_stack": True, "mixed_pointing_guard": False})
    body = _run_scan(client)
    assert "M_MIXED" in body["result"].get("auto_stacked", [])
    assert len(client.get("/api/targets/M_MIXED/stack-runs").json()) == 1


def test_mixed_pointing_guard_off_by_default_single_pointing_stacks(
        client, solved_library):
    # Even with the guard ON, a normal single-pointing target stacks (the guard
    # only fires on a clearly-bimodal batch) — so turning it on doesn't block
    # ordinary walk-away stacks.
    client.put("/api/settings", json={"mixed_pointing_guard": True})
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    assert body["result"]["stacked"] is True


def test_process_target_cancelled_during_stack_is_marked_cancelled(
    client, solved_library, monkeypatch
):
    # A Process-target job cancelled *while its stack step runs* must be
    # classified 'cancelled', not 'done'. The stack step honours the cancel and
    # returns the {"cancelled": True, "run_id": None, ...} sentinel with no run
    # written; submit_process_target must surface that at the top level so the
    # JobManager's engine_cancelled check fires. Regression: it used to set
    # stacked:True and never propagate `cancelled`, so the job showed 'done' with
    # run_id:None on the Jobs page.
    from webapp import pipeline as pl

    def fake_stack_target(settings, jm, job, lib, safe, **kwargs):
        job._cancel.set()  # user pressed cancel just as the stack aborts
        return {"cancelled": True, "run_id": None, "output_dir": "",
                "errors": [], "n_frames_used": 0, "canvas_shape": [0, 0, 0]}

    monkeypatch.setattr(pl, "_stack_target", fake_stack_target)
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "cancelled", body
    result = body["result"]
    assert result["cancelled"] is True
    assert result["stacked"] is False
    # No stack run was recorded (the cancel aborted before any output).
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) == 0


def test_process_target_skips_stack_when_nothing_solved(client, built_library):
    # No ASTAP in CI and no injected WCS → nothing is plate-solved, so the chained
    # stack is skipped with a clear reason rather than failing the whole job.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    result = body["result"]
    assert result["stacked"] is False
    assert result["stack_skipped_reason"] == "no_solved_frames"
    # QC still ran even though the stack was skipped.
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)
    # No stack run was created.
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) == 0


def _record_auto_crop(monkeypatch) -> list[bool]:
    """Wrap ``_auto_edit_process_run`` so a test can see the ``auto_crop``
    preference each unattended auto-edit was actually given."""
    from webapp import pipeline as pipeline_mod

    seen: list[bool] = []
    real = pipeline_mod._auto_edit_process_run

    def spy(lib, safe, run_id, auto_crop=True):
        seen.append(auto_crop)
        return real(lib, safe, run_id, auto_crop=auto_crop)

    monkeypatch.setattr(pipeline_mod, "_auto_edit_process_run", spy)
    return seen


def test_process_target_auto_edit_honours_the_auto_crop_setting(
        client, solved_library, monkeypatch):
    """The owner's "Auto-crop ragged border" setting reaches the *unattended*
    auto-edit too — otherwise the hands-off "Process target" picture would still be
    cropped after they turned it off in Settings."""
    seen = _record_auto_crop(monkeypatch)
    client.put("/api/settings", json={"auto_crop_border": False})
    r = client.post("/api/targets/M_42/process")
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    assert seen == [False], seen


def test_auto_stack_auto_edit_honours_the_auto_crop_setting(
        client, solved_library, monkeypatch):
    """Same for the fully-unattended watcher chain (auto-stack → auto-edit)."""
    seen = _record_auto_crop(monkeypatch)
    client.put("/api/settings", json={
        "auto_stack": True, "auto_edit_on_autostack": True,
        "auto_crop_border": False})
    _run_scan(client)
    assert seen and all(v is False for v in seen), seen


def test_auto_edit_crops_by_default_on_an_unchanged_install(
        client, solved_library, monkeypatch):
    """And the default is unchanged: an install that never touched the setting
    still gets the trimming Auto it always had."""
    seen = _record_auto_crop(monkeypatch)
    r = client.post("/api/targets/M_42/process")
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    assert seen == [True], seen


# --- The scan says what it walked past ---------------------------------------
#
# A bare "<T>/" beside "<T>_sub/" is skipped as the Seestar's own on-device
# picture. That is right for a finished picture and wrong for a plainly-named
# folder of the user's own subs, and it used to happen in silence — the owner's
# library has one of exactly the second shape.

def _drop_a_folder(data_root: Path, name: str, filenames: list[str]) -> None:
    from synth import write_seestar_fits
    d = data_root / "incoming" / name
    d.mkdir(parents=True, exist_ok=True)
    for i, fn in enumerate(filenames):
        write_seestar_fits(d / fn, n_stars=20, seed=900 + i)


def test_the_scan_reports_a_skipped_folder_it_cannot_account_for(client, data_root):
    _drop_a_folder(data_root, "NGC 6888_sub",
                   ["Light_NGC 6888_10.0s_IRCUT_0001.fit"])
    _drop_a_folder(data_root, "NGC 6888",
                   [f"Light_NGC 6888_10.0s_IRCUT_{i + 100:04d}.fit" for i in range(4)])
    body = _wait_job(client, client.post("/api/scan", json={}).json()["job_id"])
    assert body["state"] == "done", body
    [skip] = body["result"]["skipped_folders"]
    assert skip == {"name": "NGC 6888", "n_files": 4, "n_unrecognised": 4}
    # Reported, not acted on: the folder is still skipped and still on disk.
    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert "NGC_6888" in safes
    assert len(client.get("/api/targets/NGC_6888/frames").json()) == 1
    assert len(list((data_root / "incoming" / "NGC 6888").iterdir())) == 4


def test_an_ordinary_seestar_drop_says_nothing_about_its_skips(client, data_root):
    """The half that keeps this quiet: the device's own picture is skipped as
    designed, and the result carries no note at all."""
    _drop_a_folder(data_root, "M 81_sub", ["Light_M 81_10.0s_IRCUT_0001.fit"])
    _drop_a_folder(data_root, "M 81", ["Stacked.fit", "Stacked_60s.fit"])
    body = _wait_job(client, client.post("/api/scan", json={}).json()["job_id"])
    assert body["state"] == "done", body
    assert "skipped_folders" not in body["result"]
