"""`GET /api/life-list/tonight` — "of the 110 still ahead of me, which can I
actually shoot tonight?"

The life-list page's own headline invites a beginner to *"pick one and point the
scope at it tonight"*, and then shows them the catalog in Messier order — the
first dozen tiles are M1…M12, a set chosen in the 1770s with no relationship at
all to what is above the horizon this evening. This route is the missing half of
that sentence.

It introduces **no new scoring**: every assertion below that says "this object is
up" is checked against :func:`seestack.nightplan.well_placed_tonight` itself
rather than against a copy of its answer, so the life list and the Tonight page
cannot drift into two claims about the same object on the same night.

Fixed instants rather than "now", so nothing here can flip with the calendar.
"""

from __future__ import annotations

from datetime import datetime, timezone

from seestack.nightplan import (
    HorizonProfile,
    Observer,
    load_catalog,
    well_placed_tonight,
)

LONDON = {"site_lat": 51.5, "site_lon": -0.13}
#: Mid-January evening from London: Orion is up, the summer Milky Way is not.
WINTER_EVENING = "2026-01-15T20:00:00Z"
#: Mid-July, the other half of the year — the same catalog, a different sky.
SUMMER_NIGHT = "2026-07-15T23:00:00Z"


def _ids(client, when: str, **params) -> list[str]:
    r = client.get("/api/life-list/tonight", params={"when": when, **params})
    assert r.status_code == 200, r.text
    return r.json()["ids"]


def _planner_ids(when: str, *, min_alt: float = 30.0) -> list[str]:
    """The same question asked of the engine directly, with no webapp in between."""
    placed = well_placed_tonight(
        Observer(lat_deg=LONDON["site_lat"], lon_deg=LONDON["site_lon"]),
        datetime.fromisoformat(when.replace("Z", "+00:00")),
        load_catalog(),
        min_altitude_deg=min_alt,
        limit=None,
        horizon=HorizonProfile.from_pairs([]),
    )
    return [p.id for p in placed]


def test_without_a_location_it_says_nothing_rather_than_guessing(client):
    """A fresh install has no site set, so there is no honest answer — and the
    page's chip is absent rather than showing an empty or invented list."""
    body = client.get("/api/life-list/tonight").json()
    assert body["ids"] == []
    assert body["location_source"] == "none"


def test_it_names_the_objects_the_planner_names_in_the_planner_s_order(client):
    """Agreement by construction, not by a copied list: a life-list tile and a
    Tonight row must never disagree about the same object on the same night."""
    client.put("/api/settings", json=LONDON)

    got = _ids(client, WINTER_EVENING)
    assert got == _planner_ids(WINTER_EVENING)
    assert got, "expected a January evening from London to have *something* up"


def test_the_answer_is_a_genuine_subset_of_the_catalog(client):
    """The filter has to narrow, or it is not a filter — and every id it returns
    has to be one the page can actually match to a tile."""
    client.put("/api/settings", json=LONDON)
    catalog_ids = {o.id for o in load_catalog()}

    got = _ids(client, WINTER_EVENING)
    assert set(got) <= catalog_ids
    assert len(got) < len(catalog_ids), "half the sky is always below the horizon"
    assert len(set(got)) == len(got), "an object must not be offered twice"


def test_winter_and_summer_do_not_answer_the_same(client):
    """The whole point is that the sky moves. If these agreed, the route would be
    answering something other than the question."""
    client.put("/api/settings", json=LONDON)

    winter = set(_ids(client, WINTER_EVENING))
    summer = set(_ids(client, SUMMER_NIGHT))
    assert winter and summer
    assert winter != summer
    # M42 (Orion) is a winter evening object from London and is below the
    # horizon on a July night; M57 (Lyra) is the other way round.
    assert "M42" in winter and "M42" not in summer
    assert "M57" in summer and "M57" not in winter


def test_raising_the_floor_can_only_take_objects_away(client):
    """``min_alt`` is the user's own setting, and a higher one is a stricter
    question — so its answer must be contained in the looser one's. A monotonic
    property rather than a fixed count, which would pin the ephemeris."""
    client.put("/api/settings", json=LONDON)

    low = set(_ids(client, WINTER_EVENING, min_alt=20))
    high = set(_ids(client, WINTER_EVENING, min_alt=60))
    assert high <= low
    assert high != low, "20° and 60° should not be the same sky"


def test_it_reports_the_floor_it_measured_against(client):
    """The page says "climb above N°" and must not have to guess N — the answer
    carries the floor that produced it, including when the caller overrode it."""
    client.put("/api/settings", json={**LONDON, "min_target_altitude_deg": 25})

    assert client.get("/api/life-list/tonight").json()["min_altitude_deg"] == 25
    override = client.get("/api/life-list/tonight", params={"min_alt": 45}).json()
    assert override["min_altitude_deg"] == 45


def test_the_settings_floor_is_honoured_not_just_reported(client):
    """Reporting the floor and using it are two different things; a mismatch
    would make the sentence beside the tiles quietly false."""
    client.put("/api/settings", json={**LONDON, "min_target_altitude_deg": 55})

    assert _ids(client, WINTER_EVENING) == _planner_ids(WINTER_EVENING, min_alt=55.0)


def test_a_bad_when_is_refused_rather_than_silently_ignored(client):
    client.put("/api/settings", json=LONDON)
    assert client.get("/api/life-list/tonight",
                      params={"when": "not-a-timestamp"}).status_code == 422


def test_it_reads_no_project_and_writes_nothing(client, data_root):
    """This route answers from the bundled catalog and the site setting alone —
    no library walk, no project DB, no file written. It is asked on every visit
    to the page, so that has to stay true."""
    lib_dir = data_root / "library"
    before = sorted(p.name for p in lib_dir.iterdir()) if lib_dir.exists() else []

    client.put("/api/settings", json=LONDON)
    assert client.get("/api/life-list/tonight").status_code == 200

    after = sorted(p.name for p in lib_dir.iterdir()) if lib_dir.exists() else []
    assert after == before
