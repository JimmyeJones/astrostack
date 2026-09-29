"""The per-target "night after night" deepening reel endpoints."""

from __future__ import annotations

import json

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_stack(root, safe: str, name: str, *, subs: int, when: str,
               noise: float, seed: int,
               shot_from: str | None = None, shot_to: str | None = None,
               hours: list[str] | None = None) -> int:
    """Write a synthetic linear stack FITS and register a run for it."""
    lib = Library.open_or_create(root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        h = w = 48
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:h, 0:w]
        glow = 0.15 * np.exp(-(((xx - 24) ** 2 + (yy - 24) ** 2) / 200.0))
        chan = (0.1 + glow + noise * rng.standard_normal((h, w))).astype(np.float32)
        chan[22:26, 22:26] = 0.9
        cube = np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)
        fp = tdir / f"{name}.fits"
        fits.PrimaryHDU(data=cube).writeto(fp, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=when, output_basename=name,
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=subs, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=3, options_json="{}",
                capture_start_utc=shot_from, capture_end_utc=shot_to,
                capture_hours_json=(json.dumps(hours) if hours else None),
            ))
        finally:
            proj.close()
        return run_id
    finally:
        lib.close()


def test_deepening_info_self_hides_with_one_stack(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "master", subs=120, when="2026-05-01T00:00:00Z",
               noise=0.04, seed=1)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is False
    assert body["n_stacks"] == 1
    # And the animation itself 404s (nothing to show yet).
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 404


def test_deepening_info_reports_the_series(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Register out of chronological order to prove the endpoint sorts by time.
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.008, seed=3)
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=2)
    _add_stack(solved_library, safe, "s3", subs=1240, when="2026-05-28T00:00:00Z",
               noise=0.004, seed=4)

    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is True
    assert body["n_stacks"] == 3
    assert body["first_subs"] == 120       # oldest
    assert body["last_subs"] == 1240       # newest (deepest)
    assert body["first_utc"] == "2026-05-12T00:00:00Z"
    assert body["last_utc"] == "2026-05-28T00:00:00Z"
    assert body["format"] in ("webp", "png")


def test_deepening_reel_serves_a_multiframe_animation(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=5)
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.01, seed=6)

    r = client.get(f"/api/targets/{safe}/deepening-reel")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("image/webp", "image/png")

    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(r.content)) as im:
        assert getattr(im, "n_frames", 1) == 2

    # A second request is served from the signature-keyed cache (still 200).
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 200


def test_deepening_reel_rebuilds_when_a_stack_is_added(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=7)
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.01, seed=8)

    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(client.get(f"/api/targets/{safe}/deepening-reel").content)) as im:
        assert getattr(im, "n_frames", 1) == 2

    # A third night lands → the cached reel's signature is stale → rebuilt to 3.
    _add_stack(solved_library, safe, "s3", subs=1240, when="2026-05-28T00:00:00Z",
               noise=0.004, seed=9)
    with Image.open(BytesIO(client.get(f"/api/targets/{safe}/deepening-reel").content)) as im:
        assert getattr(im, "n_frames", 1) == 3


def test_deepening_info_unknown_target_404(client, solved_library):
    assert client.get("/api/targets/does_not_exist/deepening-reel/info").status_code == 404


# --- ordered by when the subs were shot, not when the stack ran ----------------


def test_reel_is_ordered_and_dated_by_when_the_subs_were_shot(client, solved_library):
    """A back catalogue reprocessed out of order: the June night happened to be
    re-stacked last, so the stack clock runs June-last and the capture clock
    June-first. The card is called "night after night", so the capture clock wins —
    the rule `webapp.capture_nights` states for every surface that says "shot on"."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "july", subs=505, when="2026-08-01T00:00:00Z",
               noise=0.008, seed=3,
               shot_from="2026-07-10T21:00:00Z", shot_to="2026-07-11T02:00:00Z")
    _add_stack(solved_library, safe, "june", subs=120, when="2026-08-02T00:00:00Z",
               noise=0.04, seed=2,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-06-10T23:00:00Z")
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is True
    assert body["dated_by"] == "capture"
    assert body["n_stacks"] == 2
    # The shallow June stack is the *first* step and the deep July one the last —
    # the reverse of the order they were stacked in.
    assert body["first_subs"] == 120
    assert body["last_subs"] == 505
    # And the reported dates are the nights, not the two August stack stamps.
    assert body["first_utc"].startswith("2026-06-10")
    assert body["last_utc"].startswith("2026-07-1")
    # The animation itself builds from that order.
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 200


def test_reel_says_when_it_only_knows_the_stack_dates(client, solved_library):
    """One run without a capture window keeps the whole series on the stack clock
    (all-or-nothing) and says so, so the caption can qualify its date range."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=2)
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.008, seed=3,
               shot_from="2026-05-19T21:00:00Z", shot_to="2026-05-19T23:00:00Z")
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["dated_by"] == "stack"
    assert body["first_utc"] == "2026-05-12T00:00:00Z"
    assert body["last_utc"] == "2026-05-20T00:00:00Z"


def test_a_reprocess_of_the_same_nights_does_not_become_a_new_reel_frame(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "n1", subs=120, when="2026-06-11T00:00:00Z",
               noise=0.04, seed=2,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-06-10T23:00:00Z")
    _add_stack(solved_library, safe, "n2", subs=505, when="2026-07-11T00:00:00Z",
               noise=0.008, seed=3,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-07-10T23:00:00Z")
    before = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert before["n_stacks"] == 2
    # "Reprocess everything" re-stacks exactly the same two nights again.
    _add_stack(solved_library, safe, "redo", subs=505, when="2026-09-01T00:00:00Z",
               noise=0.008, seed=4,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-07-10T23:00:00Z")
    after = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    # Still two steps: the same nights are not a deepening step, however many
    # times they are re-stacked.
    assert after["n_stacks"] == 2
    assert after["last_subs"] == 505


def test_reel_info_says_when_the_series_steps_back_in_depth(client, solved_library):
    """Ordered by the subs' own clock, a night stacked on its own lands last with
    the fewest subs in it — so the card must not promise "more subs each time".

    `depth_monotone` is that one fact, additive: an older frontend ignores it and
    an older backend omits it, which keeps the sentence the card always had."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "n1", subs=100, when="2026-06-11T00:00:00Z",
               noise=0.04, seed=2,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-06-10T23:00:00Z")
    _add_stack(solved_library, safe, "n1_2", subs=200, when="2026-07-11T00:00:00Z",
               noise=0.02, seed=3,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-07-10T23:00:00Z")
    _add_stack(solved_library, safe, "tonight", subs=30, when="2026-08-11T00:00:00Z",
               noise=0.07, seed=4,
               shot_from="2026-08-10T21:00:00Z", shot_to="2026-08-10T23:00:00Z")
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["dated_by"] == "capture"
    assert (body["first_subs"], body["last_subs"]) == (100, 30)
    assert body["depth_monotone"] is False


def test_reel_info_reports_a_series_that_only_deepens(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "n1", subs=100, when="2026-06-11T00:00:00Z",
               noise=0.04, seed=2,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-06-10T23:00:00Z")
    _add_stack(solved_library, safe, "n1_2", subs=200, when="2026-07-11T00:00:00Z",
               noise=0.02, seed=3,
               shot_from="2026-06-10T21:00:00Z", shot_to="2026-07-10T23:00:00Z")
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["depth_monotone"] is True


# --- the reel from history: night 1; nights 1-2; ... -------------------------


def _night_of(day: str, *hours: str) -> list[str]:
    """On-the-hour UTC stamps in one evening, as `capture_hours_json` records
    them (see `seestack.stack.stacker._capture_hours`)."""
    return [f"{day}T{h}:00:00Z" for h in hours]


def test_a_cumulative_history_is_reported_as_nights_not_stacks(
        client, solved_library):
    """The owner asked for "night 1; nights 1-2; ..." and re-stacks as the nights
    come in — so on his own library the reel he asked for is *already there*, in
    stacks that exist. The endpoint now says so, and nothing is re-stacked to
    find out."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    n1 = _night_of("2026-05-01", "21", "22")
    n2 = _night_of("2026-05-02", "21", "22")
    n3 = _night_of("2026-05-03", "21")
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-02T09:00:00Z",
               noise=0.04, seed=2,
               shot_from=n1[0], shot_to=n1[-1], hours=n1)
    _add_stack(solved_library, safe, "s2", subs=240, when="2026-05-03T09:00:00Z",
               noise=0.02, seed=3,
               shot_from=n1[0], shot_to=n2[-1], hours=n1 + n2)
    _add_stack(solved_library, safe, "s3", subs=300, when="2026-05-04T09:00:00Z",
               noise=0.01, seed=4,
               shot_from=n1[0], shot_to=n3[-1], hours=n1 + n2 + n3)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is True
    assert body["dated_by"] == "capture"
    assert body["night_steps"] == [1, 2, 3]
    # The animation builds, and its frames carry the progression in their labels.
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 200


def test_a_history_that_is_not_cumulative_says_nothing_about_nights(
        client, solved_library):
    """"I re-stacked just tonight's subs" is a step the reel deliberately keeps
    (it is a fact about the library) and one this must not number: its nights are
    not a superset of the step before it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    n1 = _night_of("2026-05-01", "21", "22")
    n2 = _night_of("2026-05-02", "21", "22")
    _add_stack(solved_library, safe, "s1", subs=240, when="2026-05-02T09:00:00Z",
               noise=0.04, seed=2,
               shot_from=n1[0], shot_to=n1[-1], hours=n1)
    _add_stack(solved_library, safe, "s2", subs=30, when="2026-05-03T09:00:00Z",
               noise=0.02, seed=3,
               shot_from=n2[0], shot_to=n2[-1], hours=n2)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["dated_by"] == "capture"
    assert body["night_steps"] is None


def test_a_run_from_before_capture_hours_silences_the_night_count(
        client, solved_library):
    """The owner's library holds hundreds of runs recorded before schema 19. A
    series with a hole in it cannot be *shown* to be nested, so it keeps the
    labelling it has always had rather than guessing at a step's nights."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    n1 = _night_of("2026-05-01", "21", "22")
    n2 = _night_of("2026-05-02", "21")
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-02T09:00:00Z",
               noise=0.04, seed=2,
               shot_from=n1[0], shot_to=n1[-1])            # no hours recorded
    _add_stack(solved_library, safe, "s2", subs=240, when="2026-05-03T09:00:00Z",
               noise=0.02, seed=3,
               shot_from=n1[0], shot_to=n2[-1], hours=n1 + n2)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["night_steps"] is None


def test_a_stack_dated_series_is_never_numbered_by_nights(
        client, solved_library):
    """A `dated_by == "stack"` series is ordered by when somebody pressed Stack.
    Numbering those "night 1, nights 1-2" would be a claim about an order the
    series is not in — even when the hours themselves happen to nest."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    n1 = _night_of("2026-05-01", "21", "22")
    n2 = _night_of("2026-05-02", "21")
    # The first run records hours but no window, so `deepening_series` falls back
    # to the stack clock for the whole series (all-or-nothing, by design).
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-02T09:00:00Z",
               noise=0.04, seed=2, hours=n1)
    _add_stack(solved_library, safe, "s2", subs=240, when="2026-05-03T09:00:00Z",
               noise=0.02, seed=3,
               shot_from=n1[0], shot_to=n2[-1], hours=n1 + n2)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["dated_by"] == "stack"
    assert body["night_steps"] is None


def test_the_reel_rebuilds_when_the_night_numbering_changes(
        client, solved_library):
    """The "Nights 1-3" prefixes are a function of the observer's longitude, so a
    cached reel built before a site was set must not keep the labels it got from
    the old noon-to-noon buckets. The signature folds the steps in, which is what
    makes that a rebuild rather than a stale file."""
    from webapp.routers.stack import _deepening_signature

    runs = [_StubRun(1), _StubRun(2)]
    bare = _deepening_signature(runs, "capture")
    assert _deepening_signature(runs, "capture", None) == bare
    assert _deepening_signature(runs, "capture", [1, 2]) != bare
    assert _deepening_signature(runs, "capture", [1, 3]) != \
        _deepening_signature(runs, "capture", [1, 2])


class _StubRun:
    """Just enough of a run row for the signature: an id and a missing file
    (which the signature handles as `0:0` rather than raising)."""

    def __init__(self, run_id: int) -> None:
        self.id = run_id
        self.fits_path = f"/nonexistent/{run_id}.fits"
