"""My life list: which famous objects the owner has captured.

Read-only and offline — the catalog ships with the app and the match reads only
the target registry, so these run against a real Library with no ASTAP and no
network.
"""

from __future__ import annotations

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow


def _register(data_root, name: str, ra: float | None, dec: float | None,
              *, n_frames: int = 6, preview: str | None = None) -> str:
    """Put one solved target in the registry, as a real ingest would leave it.

    Goes through the real Library/Project API and ``refresh_target_stats`` so
    the registry row is exactly the shape an ingest (and a stack, when
    ``preview`` is given) leaves behind.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
        try:
            proj.add_frames([
                FrameRow(source_path=f"{entry.safe_name}-{i}.fit")
                for i in range(n_frames)
            ])
            if preview is not None:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-02T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=preview, n_frames_used=n_frames,
                    canvas_h=320, canvas_w=480,
                    coverage_min=1, coverage_max=n_frames, options_json="{}",
                ))
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
        return entry.safe_name
    finally:
        lib.close()


def test_an_empty_library_offers_the_whole_messier_list_to_shoot(client, data_root):
    body = client.get("/api/life-list").json()

    assert body["counts"]["messier_total"] == 110
    assert body["counts"]["messier_captured"] == 0
    assert body["counts"]["other_total"] > 0
    assert body["counts"]["other_captured"] == 0
    # Nothing is captured, but every object is still listed — the point of the
    # feature is the bucket list, so an empty library must not be an empty page.
    assert len(body["messier"]) == 110
    assert all(e["captured"] is False for e in body["messier"])


def test_the_list_reads_in_the_order_a_beginner_counts(client, data_root):
    ids = [e["catalog_id"] for e in client.get("/api/life-list").json()["messier"]]
    assert ids == [f"M{n}" for n in range(1, 111)]


def test_each_tile_carries_what_it_needs_to_explain_itself(client, data_root):
    m1 = next(
        e for e in client.get("/api/life-list").json()["messier"]
        if e["catalog_id"] == "M1"
    )
    assert m1["name"] == "Crab Nebula"
    assert m1["type"] == "supernova remnant"
    assert m1["con"] == "Tau"
    # The plain-language blurb the object-info card already uses — so an
    # uncaptured tile is a reason to go and shoot it, not just a grey box.
    assert "light-years" in m1["blurb"]


def test_a_captured_target_lights_up_its_object_and_links_to_it(client, data_root):
    safe = _register(data_root, "M 31", 10.685, 41.269)

    body = client.get("/api/life-list").json()
    m31 = next(e for e in body["messier"] if e["catalog_id"] == "M31")
    assert m31["captured"] is True
    assert m31["safe_name"] == safe
    assert m31["target_name"] == "M 31"
    assert m31["sep_deg"] < 0.01
    assert body["counts"]["messier_captured"] == 1
    # Nothing stacked yet, so there is no picture to show — the tile still
    # lights up, it just has no thumbnail.
    assert m31["thumbnail_url"] is None


def test_a_stacked_capture_offers_its_picture(client, data_root, tmp_path):
    preview = tmp_path / "preview.png"
    preview.write_bytes(b"\x89PNG\r\n\x1a\n")
    safe = _register(data_root, "M 31", 10.685, 41.269, preview=str(preview))

    m31 = next(
        e for e in client.get("/api/life-list").json()["messier"]
        if e["catalog_id"] == "M31"
    )
    assert m31["thumbnail_url"] == f"/api/targets/{safe}/thumbnail"
    # ...and the URL it hands out actually serves.
    assert client.get(m31["thumbnail_url"]).status_code == 200


def test_a_preview_the_registry_points_at_but_disk_lost_offers_no_thumbnail(
    client, data_root, tmp_path,
):
    """A tile must never hand the UI a URL that 404s — the same existence test
    ``/api/targets`` does for ``has_preview``."""
    _register(data_root, "M 31", 10.685, 41.269,
              preview=str(tmp_path / "gone.png"))

    m31 = next(
        e for e in client.get("/api/life-list").json()["messier"]
        if e["catalog_id"] == "M31"
    )
    assert m31["captured"] is True
    assert m31["thumbnail_url"] is None


def test_an_unsolved_target_leaves_its_object_grey(client, data_root):
    """No plate-solved centre means nothing to match on — the list never guesses
    from the folder name."""
    _register(data_root, "M 31", None, None)

    body = client.get("/api/life-list").json()
    assert body["counts"]["messier_captured"] == 0
    assert all(e["captured"] is False for e in body["messier"])


def test_a_registered_target_with_no_frames_is_not_a_capture(client, data_root):
    _register(data_root, "M 31", 10.685, 41.269, n_frames=0)

    assert client.get("/api/life-list").json()["counts"]["messier_captured"] == 0


def test_pointing_somewhere_else_claims_nothing(client, data_root):
    """A blank patch of sky must not light up a neighbour."""
    _register(data_root, "Random field", 150.0, 12.0)

    body = client.get("/api/life-list").json()
    assert body["counts"]["messier_captured"] == 0
    assert body["counts"]["other_captured"] == 0


def test_the_popular_ngc_ic_objects_are_listed_and_matchable(client, data_root):
    """The bundled non-Messier set is the other half of the bucket list."""
    _register(data_root, "North America Nebula", 314.75, 44.367)

    body = client.get("/api/life-list").json()
    assert body["counts"]["other_captured"] == 1
    ngc7000 = next(e for e in body["other"] if e["catalog_id"] == "NGC 7000")
    assert ngc7000["captured"] is True
    # ...and it is kept out of the Messier milestone count, which is finite.
    assert body["counts"]["messier_captured"] == 0
    assert all(not e["catalog_id"].startswith("NGC") for e in body["messier"])


def test_three_nights_on_one_object_still_read_as_one_capture(client, data_root):
    """The Seestar writes a new folder per night, so an unmerged target is
    several rows — the collection view must still say "got it", once."""
    _register(data_root, "M 31", 10.70, 41.28)
    closest = _register(data_root, "M 31 again", 10.685, 41.269)
    _register(data_root, "M 31 third night", 10.66, 41.25)

    body = client.get("/api/life-list").json()
    assert body["counts"]["messier_captured"] == 1
    m31 = next(e for e in body["messier"] if e["catalog_id"] == "M31")
    assert m31["safe_name"] == closest      # the closest centre wins, deterministically


def test_the_life_list_is_read_only(client, data_root):
    """It must never mutate the library — a beginner refreshing a page they
    like should not change anything."""
    _register(data_root, "M 31", 10.685, 41.269)
    before = client.get("/api/targets").json()

    client.get("/api/life-list")
    client.get("/api/life-list")

    assert client.get("/api/targets").json() == before
