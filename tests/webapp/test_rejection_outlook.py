"""The walk-away chain's rejection, answered *before* the night.

The Stack form already asks "can the rejection I picked actually drop a lone
satellite trail?" of the values on screen, and ``seestack.stackhealth`` asks it
of the finished picture. Neither reaches the path that matters most to a
walk-away owner: the watcher's auto-stack and the one-click **Process target**
button both stack with ``_stack_target(auto=True)``, which only picks a method
when the user picked none — so an owner who once saved ``sigma_clip`` into a
per-target default gets plain κ-σ on *every* unattended stack, silently reaching
nothing on any night (or any mosaic panel) thinner than ``kappa_min_frames``.

These pin ``GET /api/targets/{safe}/rejection-outlook``: that it resolves what
the chain would resolve (through the *same* helpers, so the two cannot drift),
that it is judged by a mosaic's per-pixel depth rather than its frame count, and
that it withholds a verdict rather than guessing when there is no stack to have
an opinion about.
"""

from __future__ import annotations

from seestack.io.library import Library



def _frames_at(data_root, safe: str, pointings: list[tuple[float, float, int]]) -> None:
    """Re-point the target's frames, cloning rows until each pointing has N.

    ``pointings`` is ``[(ra, dec, count), …]``. Rows are cloned from the
    fixture's own frames, so every one keeps a real ``source_path`` and WCS —
    ``estimate_stack`` only reads the DB, never the files.
    """
    from dataclasses import replace

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            rows = list(proj.iter_frames())
            template = rows[0]
            for r in rows:
                proj.update_frame(r.id, accept=False)
            n = 0
            for ra, dec, count in pointings:
                for _ in range(count):
                    n += 1
                    proj.add_frame(replace(
                        template, id=None, accept=True,
                        # ``source_path`` is UNIQUE, and nothing here opens it.
                        source_path=f"{template.source_path}.{n:03d}",
                        ra_center_deg=ra, dec_center_deg=dec,
                    ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _safe(client) -> str:
    """The fixture library's first target, by its own safe name."""
    return client.get("/api/targets").json()[0]["safe_name"]


def _outlook(client, safe: str) -> dict:
    r = client.get(f"/api/targets/{safe}/rejection-outlook")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_saved_sigma_clip_default_reports_that_it_cannot_reach_a_lone_trail(
        client, solved_library):
    """The bug this endpoint exists for: 6 subs, sigma clipping saved as the
    target's default, so every unattended stack runs κ-σ and clips nothing."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 6)])
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": True})

    out = _outlook(client, safe)
    assert out["method"] == "sigma-clip"
    assert out["n_frames"] == 6
    assert out["reaches"] is False
    # 11 at the default κ=3 — the count κ-σ first stands a chance at.
    assert out["lone_outlier_min_frames"] == 11
    # And it was the *user's* setting, which is the only case worth saying
    # anything about.
    assert out["user_chose"] is True


def test_the_same_target_deep_enough_reaches_and_says_so(client, solved_library):
    """Same saved setting, past the κ-σ floor: no caution, so nothing to say."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 20)])
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": True})

    out = _outlook(client, safe)
    assert out["method"] == "sigma-clip"
    assert out["reaches"] is True


def test_a_target_with_nothing_saved_gets_the_chains_own_auto_pick(
        client, solved_library):
    """No saved choice → the chain injects ``auto_reject``, which resolves to
    min/max down here and *does* reach. The app doing its job, not a warning."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 6)])

    out = _outlook(client, safe)
    assert out["user_chose"] is False
    assert out["method"] == "min-max-reject"
    assert out["reaches"] is True


def test_a_mosaic_is_judged_by_its_panel_depth_not_its_frame_count(
        client, solved_library):
    """Four panels 5 subs deep is 20 frames and a *pixel* depth of 5 — past
    κ-σ's 11-frame floor on the count, nowhere near it on the pixels that make
    the picture."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [
        (83.6, -5.4, 5), (84.4, -5.4, 5), (83.6, -4.6, 5), (84.4, -4.6, 5),
    ])
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": True})

    out = _outlook(client, safe)
    assert out["n_frames"] == 20
    assert out["panel_depth"] == 5
    # 20 >= 11 would say "reaches"; the honest per-pixel answer is 5 < 11.
    assert out["reaches"] is False


def test_a_single_field_reports_no_panel_depth(client, solved_library):
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 20)])
    out = _outlook(client, safe)
    assert out["panel_depth"] is None


def test_a_target_with_nothing_solved_withholds_a_verdict(client, built_library):
    """No WCS anywhere (the ``built_library`` fixture never solves), so there is
    no stack to have an opinion about — 200 with no verdict, not a 422 the page
    would render as an error."""
    safe = _safe(client)
    out = _outlook(client, safe)
    assert out["reaches"] is None


def test_a_malformed_saved_defaults_row_falls_back_instead_of_500ing(
        client, solved_library):
    """The same degradation the walk-away job makes: a hand-edited/legacy meta
    row that is valid JSON but not an object reads as "nothing saved"."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 6)])
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta("web_stack_defaults", "[1, 2, 3]")
        finally:
            proj.close()
    finally:
        lib.close()

    out = _outlook(client, safe)
    assert out["user_chose"] is False
    assert out["reaches"] is True


def test_the_endpoint_resolves_exactly_what_the_walkaway_chain_resolves(
        client, solved_library):
    """The whole point of the shared helpers: the options the page speaks about
    are the options the job will stack with. Asserted against the *chain's* own
    merge rather than against a second copy of the rule."""
    safe = _safe(client)
    from webapp.config import Settings
    from webapp.schemas import strip_non_form_keys
    from webapp.walkaway import apply_unattended_rejection, parse_saved_stack_defaults

    _frames_at(solved_library, safe, [(83.6, -5.4, 6)])
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": True})

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            raw = proj.get_meta("web_stack_defaults")
        finally:
            proj.close()
    finally:
        lib.close()

    opts = strip_non_form_keys(Settings().default_stack_options)
    opts.update(parse_saved_stack_defaults(raw))
    apply_unattended_rejection(opts)
    # The user's saved κ-σ survives; the chain adds nothing on top of it.
    assert opts["sigma_clip"] is True
    assert "auto_reject" not in opts

    out = _outlook(client, safe)
    assert out["method"] == "sigma-clip"


def test_the_outlook_never_writes_anything(client, solved_library):
    """Read-only: asking the question must not save a default or start a stack."""
    safe = _safe(client)
    _frames_at(solved_library, safe, [(83.6, -5.4, 6)])
    before = client.get(f"/api/targets/{safe}/stack-defaults").json()
    _outlook(client, safe)
    assert client.get(f"/api/targets/{safe}/stack-defaults").json() == before
    assert client.get("/api/jobs").json() == []
