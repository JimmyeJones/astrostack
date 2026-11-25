"""A target whose display name is another target's folder name must not take
over that target's URL (Scout 2026-11-25, sweep 4).

"M 31" lives in folder ``M_31``; a later "M_31" gets ``M_31-<hash>``. Before the
fix, ``Library.find_target("M_31")`` (``name = ? OR safe_name = ?``) answered with
the "M_31" row, so the "M 31" card's link opened the other target, DELETE
removed the wrong one and a re-scan of "M 31" reported the other name.
"""

from __future__ import annotations

import pytest

from seestack.io.library import Library

ORDERS = [("M 31", "M_31"), ("M_31", "M 31")]


def _make(data_root, names):
    lib = Library.open_or_create(data_root / "library")
    try:
        made = {}
        for n in names:
            entry, proj = lib.open_or_create_target(n)
            proj.close()
            made[n] = entry.safe_name
        return made
    finally:
        lib.close()


@pytest.mark.parametrize("names", ORDERS)
def test_each_target_page_answers_its_own_folder(client, data_root, names):
    made = _make(data_root, names)
    assert len(set(made.values())) == 2
    for name, safe in made.items():
        r = client.get(f"/api/targets/{safe}")
        assert r.status_code == 200
        assert r.json()["name"] == name
        assert r.json()["safe_name"] == safe


@pytest.mark.parametrize("names", ORDERS)
def test_delete_removes_the_target_whose_folder_was_named(client, data_root, names):
    made = _make(data_root, names)
    victim = made["M 31"]           # the one whose folder is ``M_31`` or hashed
    r = client.delete(f"/api/targets/{victim}")
    assert r.status_code in (200, 204)
    left = {t["name"]: t["safe_name"] for t in client.get("/api/targets").json()}
    assert "M 31" not in left
    assert left.get("M_31") == made["M_31"]


@pytest.mark.parametrize("names", ORDERS)
def test_rescan_reopens_the_same_target_by_display_name(data_root, names):
    made = _make(data_root, names)
    lib = Library.open_or_create(data_root / "library")
    try:
        for name, safe in made.items():
            entry, proj = lib.open_or_create_target(name)
            proj.close()
            assert (entry.name, entry.safe_name) == (name, safe)
            # Folder lookup answers the folder's owner; display lookup the name's.
            assert lib.find_target(safe).name == name
            assert lib.find_target_by_name(name).safe_name == safe
    finally:
        lib.close()


def test_display_lookup_still_finds_a_renamed_target_by_its_folder(data_root):
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.open_or_create_target("NGC 6888_SUB")
        proj.close()
        lib.rename_target(entry.safe_name, "Crescent Nebula")
        assert lib.find_target_by_name("Crescent Nebula").safe_name == entry.safe_name
        assert lib.find_target_by_name(entry.safe_name).name == "Crescent Nebula"
        assert lib.find_target("Crescent Nebula").safe_name == entry.safe_name
    finally:
        lib.close()
