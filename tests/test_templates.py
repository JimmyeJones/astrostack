"""Template save/load/list/delete."""

import json

import pytest

from seestack.gui.templates import (
    delete_template,
    list_templates,
    load_template,
    save_template,
    templates_dir,
)
from seestack.stack.stacker import StackOptions


@pytest.fixture(autouse=True)
def isolated_templates(tmp_path, monkeypatch):
    """Redirect templates_dir() at the platformdirs layer so tests don't
    pollute the real user data dir."""
    monkeypatch.setattr(
        "seestack.gui.templates.user_data_dir",
        lambda *_a, **_kw: str(tmp_path),
    )


def test_save_load_roundtrip():
    opts = StackOptions(
        sigma_kappa=2.7, drizzle=True, drizzle_scale=1.8,
        quality_weighted=True, lucky_fraction=0.5,
        output_name="m31_widefield",
    )
    save_template("M31 widefield", opts)
    loaded = load_template("M31 widefield")
    assert loaded.sigma_kappa == 2.7
    assert loaded.drizzle is True
    assert loaded.drizzle_scale == 1.8
    assert loaded.quality_weighted is True
    assert loaded.lucky_fraction == 0.5
    assert loaded.output_name == "m31_widefield"


def test_list_templates_sorted():
    save_template("Bravo", StackOptions())
    save_template("alpha", StackOptions())
    save_template("Charlie", StackOptions())
    names = list_templates()
    # Case-insensitive alpha sort.
    assert [n.lower() for n in names] == ["alpha", "bravo", "charlie"]


def test_delete_template():
    save_template("Doomed", StackOptions())
    assert "Doomed" in list_templates()
    delete_template("Doomed")
    assert "Doomed" not in list_templates()


def test_save_strips_unsafe_filename_chars():
    save_template("With:Bad/Chars*", StackOptions(sigma_kappa=2.9))
    loaded = load_template("With:Bad/Chars*")  # should still load via same name
    assert loaded.sigma_kappa == 2.9


def test_load_tolerates_unknown_keys():
    """Future versions might add new fields. Older templates should still load."""
    path = templates_dir() / "future.seestackpreset.json"
    payload = {"sigma_kappa": 3.3, "future_option": "ignore-me"}
    path.write_text(json.dumps(payload))
    loaded = load_template("future")
    assert loaded.sigma_kappa == 3.3
